"""
The JD Extraction Service — Phase 1 Intelligence Core.
Powered by Google Gemini (google-genai SDK).

Features:
1. Uses google-genai async client (non-blocking).
2. In-memory MD5-keyed cache prevents redundant Gemini calls for identical JDs.
3. Service is instantiated ONCE (singleton in app state) — no per-request overhead.
4. Retry with exponential backoff + model fallback chain for 503/429 errors.
"""

import json
import hashlib
import logging
import asyncio
from google import genai
from google.genai import types

from app.core.config import get_settings
from app.models.jd_models import JDExtractionResult

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# In-memory JD extraction cache
# Key: MD5 of raw JD text  |  Value: validated JDExtractionResult
# ─────────────────────────────────────────────────────────────
_jd_cache: dict[str, JDExtractionResult] = {}


# ─────────────────────────────────────────────────────────────
# SYSTEM PROMPT — The Heart of Phase 1
# ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
You are an expert Technical Recruiter and Intelligence Extraction System.
Your task is to parse a raw Job Description (JD) and extract ALL meaningful
hiring signals into a structured JSON object.

CRITICAL RULES:
1. You MUST return ONLY a valid JSON object. No explanations, no markdown, no prose.
2. Extract skills into TWO distinct categories:
   - must_have_skills: Non-negotiable. Absence = candidate should be rejected.
   - nice_to_have_skills: Preferred but not blockers.
3. For minimum_years_experience: if a range is given (e.g., "5-9 years"),
   use the LOWER bound as an integer. NEVER return null — use 0 if unknown.
4. Behavioral traits: Look for culture/work-style signals (e.g., "bias for action",
   "async-first", "comfortable with ambiguity"). These are often implicit.
5. Disqualifiers: Extract EXPLICIT anti-patterns mentioned in the JD
   (e.g., "no consulting-only backgrounds", "no pure research roles").
6. Domain knowledge: Areas of expertise beyond named technologies.
7. preferred_company_types: If the JD mentions preferring or penalizing certain company types.
8. remote_ok: Set to true only if the JD explicitly says remote or WFH is OK.
9. extraction_confidence: Set to "high" if the JD is detailed, "medium" if ambiguous, "low" if vague.

OUTPUT JSON SCHEMA (return EXACTLY this structure):
{
  "job_title": "<string>",
  "minimum_years_experience": <integer, never null, use 0 if unknown>,
  "maximum_years_experience": <integer or null>,
  "must_have_skills": ["<string>", ...],
  "nice_to_have_skills": ["<string>", ...],
  "behavioral_traits": ["<string>", ...],
  "domain_knowledge": ["<string>", ...],
  "disqualifiers": ["<string>", ...],
  "preferred_locations": ["<string>", ...],
  "remote_ok": <boolean>,
  "preferred_notice_period_days": <integer or null>,
  "preferred_company_types": ["<string>", ...],
  "key_responsibilities_summary": "<2-3 sentence summary>",
  "extraction_confidence": "<high|medium|low>"
}
"""


# ─────────────────────────────────────────────────────────────
# SERVICE CLASS
# ─────────────────────────────────────────────────────────────

class JDExtractionService:
    """
    Encapsulates all logic for the JD → structured JSON extraction pipeline.

    Instantiated ONCE at app startup via lifespan and stored in app.state.
    Uses google-genai async client so it never blocks FastAPI's event loop.
    """

    # Fallback model chain — tried in order when primary is unavailable (503)
    FALLBACK_MODELS = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    ]

    def __init__(self):
        self.settings = get_settings()
        self.client = genai.Client(api_key=self.settings.GEMINI_API_KEY)
        logger.info(f"JDExtractionService initialized | model={self.settings.GEMINI_MODEL}")

    async def extract(self, raw_jd_text: str) -> JDExtractionResult:
        """
        Main extraction pipeline with in-memory caching.

        Args:
            raw_jd_text: The raw, unstructured job description text.

        Returns:
            A validated JDExtractionResult Pydantic model.

        Raises:
            ValueError: If the LLM response cannot be parsed or validated.
            RuntimeError: If the Gemini API call fails.
        """
        # ── Cache check ───────────────────────────────────────
        cache_key = hashlib.md5(raw_jd_text.strip().encode()).hexdigest()
        if cache_key in _jd_cache:
            logger.info(f"Cache HIT for JD (md5={cache_key[:8]}...) — skipping Gemini call")
            return _jd_cache[cache_key]

        logger.info(f"Cache MISS | Starting JD extraction | text_length={len(raw_jd_text)}")

        # ── Step 1: Call Gemini API ───────────────────────────
        raw_response = await self._call_gemini(raw_jd_text)

        # ── Step 2: Parse JSON from LLM response ─────────────
        extracted_dict = self._parse_json_response(raw_response)

        # ── Step 3: Validate with Pydantic ───────────────────
        validated_result = self._validate_schema(extracted_dict)

        # ── Step 4: Store in cache ────────────────────────────
        _jd_cache[cache_key] = validated_result

        logger.info(
            f"Extraction complete | job_title='{validated_result.job_title}' "
            f"| must_have_count={len(validated_result.must_have_skills)} "
            f"| disqualifiers_count={len(validated_result.disqualifiers)} "
            f"| confidence={validated_result.extraction_confidence}"
        )

        return validated_result

    async def _call_gemini(self, raw_jd_text: str) -> str:
        """
        Calls the Google Gemini API asynchronously with JSON output enforced.

        Retry strategy:
        - Tries each model in FALLBACK_MODELS (2.5-flash -> 2.0-flash -> 1.5-flash)
        - Per model: up to 3 attempts with 2s, 4s exponential backoff
        - Retries on 503 (high demand) and 429 (rate limit)
        - Fails fast on 400, 401, 404 etc.
        """
        user_message = (
            f"Extract all hiring signals from this Job Description:\n\n"
            f"---BEGIN JD---\n{raw_jd_text}\n---END JD---\n\n"
            f"Return ONLY a valid JSON object matching the schema. No markdown, no prose."
        )

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=self.settings.LLM_TEMPERATURE,
            max_output_tokens=self.settings.LLM_MAX_TOKENS,
            response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(
                thinking_budget=0
            ),
        )

        # Configured model first, then fallbacks
        primary = self.settings.GEMINI_MODEL
        models_to_try = [primary] + [m for m in self.FALLBACK_MODELS if m != primary]

        last_error = None

        for model in models_to_try:
            for attempt in range(1, 4):   # 3 attempts per model
                try:
                    logger.info(f"Gemini call | model={model} | attempt={attempt}")
                    response = await self.client.aio.models.generate_content(
                        model=model,
                        contents=user_message,
                        config=config,
                    )
                    raw_content = response.text
                    logger.debug(f"Gemini response: {raw_content[:200]}...")
                    logger.info(f"Gemini success | model={model}")
                    return raw_content

                except Exception as e:
                    err_str = str(e)
                    last_error = e

                    is_retryable = ("503" in err_str or "UNAVAILABLE" in err_str
                                    or "429" in err_str or "RESOURCE_EXHAUSTED" in err_str)

                    if is_retryable and attempt < 3:
                        wait = 2 ** attempt   # 2s, 4s
                        logger.warning(
                            f"Gemini {err_str[:80]}... | model={model} "
                            f"| attempt={attempt} | retrying in {wait}s"
                        )
                        await asyncio.sleep(wait)
                        continue

                    if is_retryable:
                        logger.warning(f"All retries exhausted for model={model}, trying fallback")
                        break   # move to next model

                    # Non-retryable (401, 400, etc) — fail immediately
                    logger.error(f"Gemini non-retryable error: {e}")
                    raise RuntimeError(f"Gemini API call failed: {e}")

        raise RuntimeError(
            f"Gemini unavailable across all fallback models. Last error: {last_error}"
        )

    def _parse_json_response(self, raw_response: str) -> dict:
        """
        Parses the raw LLM string into a Python dictionary.
        Includes defensive stripping for edge-case markdown fences.
        """
        try:
            cleaned = raw_response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1])
            return json.loads(cleaned)

        except json.JSONDecodeError as e:
            pos = e.pos
            start = max(0, pos - 100)
            end = min(len(raw_response), pos + 100)
            context = raw_response[start:end]
            logger.error(f"JSON parse failed | error={e} | context_around_error='{context}' | raw={raw_response}")
            raise ValueError(
                f"LLM returned invalid JSON. Parse error: {e}. "
                f"Context: ... {context} ..."
            )

    def _validate_schema(self, extracted_dict: dict) -> JDExtractionResult:
        """
        Validates the parsed dictionary against the Pydantic JDExtractionResult schema.
        """
        try:
            return JDExtractionResult(**extracted_dict)
        except Exception as e:
            logger.error(f"Pydantic validation failed: {e}")
            raise ValueError(f"Extracted data failed schema validation: {e}")
