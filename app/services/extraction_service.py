"""
The JD Extraction Service — Phase 1 Intelligence Core.

Fixes applied:
1. Uses AsyncGroq (non-blocking) instead of sync Groq client.
2. In-memory MD5-keyed cache prevents redundant Groq calls for identical JDs.
3. Service is instantiated ONCE (singleton in app state) — no per-request overhead.
"""

import json
import hashlib
import logging
import asyncio
from groq import AsyncGroq, APIConnectionError, APIStatusError

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
   use the LOWER bound as an integer.
4. Behavioral traits: Look for culture/work-style signals (e.g., "bias for action",
   "async-first", "comfortable with ambiguity"). These are often implicit.
5. Disqualifiers: Extract EXPLICIT anti-patterns mentioned in the JD
   (e.g., "no consulting-only backgrounds", "no pure research roles").
   These are CRITICAL for accurate ranking — most JDs don't have them but when
   they do, they are the strongest signal of all.
6. Domain knowledge: Areas of expertise beyond named technologies
   (e.g., "information retrieval", "A/B testing", "marketplace dynamics").
7. preferred_company_types: If the JD mentions preferring or penalizing
   certain company types (product vs consulting vs FAANG), extract them.
8. remote_ok: Set to true only if the JD explicitly says remote or WFH is OK.
9. extraction_confidence: Set to "high" if the JD is detailed,
   "medium" if ambiguous, "low" if very vague.

OUTPUT JSON SCHEMA (return EXACTLY this structure):
{
  "job_title": "<string>",
  "minimum_years_experience": <integer>,
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
  "key_responsibilities_summary": "<2-3 sentence summary of actual day-to-day work>",
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
    Uses AsyncGroq so it never blocks FastAPI's event loop.
    """

    def __init__(self):
        self.settings = get_settings()
        # AsyncGroq: non-blocking — critical for FastAPI concurrency
        self.client = AsyncGroq(api_key=self.settings.GROQ_API_KEY)
        logger.info(f"JDExtractionService initialized | model={self.settings.GROQ_MODEL}")

    async def extract(self, raw_jd_text: str) -> JDExtractionResult:
        """
        Main extraction pipeline with in-memory caching.

        Args:
            raw_jd_text: The raw, unstructured job description text.

        Returns:
            A validated JDExtractionResult Pydantic model.

        Raises:
            ValueError: If the LLM response cannot be parsed or validated.
            RuntimeError: If the Groq API call fails.
        """
        # ── Cache check ───────────────────────────────────────
        cache_key = hashlib.md5(raw_jd_text.strip().encode()).hexdigest()
        if cache_key in _jd_cache:
            logger.info(f"Cache HIT for JD (md5={cache_key[:8]}...) — skipping Groq call")
            return _jd_cache[cache_key]

        logger.info(f"Cache MISS | Starting JD extraction | text_length={len(raw_jd_text)}")

        # ── Step 1: Call Groq API (async) ─────────────────────
        raw_response = await self._call_groq(raw_jd_text)

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

    async def _call_groq(self, raw_jd_text: str) -> str:
        """
        Calls the Groq Chat Completions API with JSON mode enforced.
        Uses AsyncGroq so this is truly non-blocking.
        """
        try:
            response = await self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Extract all hiring signals from this Job Description:\n\n"
                            f"---BEGIN JD---\n{raw_jd_text}\n---END JD---"
                        )
                    }
                ],
                model=self.settings.GROQ_MODEL,
                temperature=self.settings.LLM_TEMPERATURE,
                max_tokens=self.settings.LLM_MAX_TOKENS,
                response_format={"type": "json_object"},  # ← Forces pure JSON output
            )

            raw_content = response.choices[0].message.content
            logger.debug(f"Groq raw response: {raw_content[:200]}...")
            return raw_content

        except APIConnectionError as e:
            logger.error(f"Groq API connection failed: {e}")
            raise RuntimeError(f"Could not connect to Groq API: {e}")

        except APIStatusError as e:
            logger.error(f"Groq API error {e.status_code}: {e.message}")
            raise RuntimeError(f"Groq API returned error {e.status_code}: {e.message}")

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
            logger.error(f"JSON parse failed | error={e} | raw={raw_response[:300]}")
            raise ValueError(
                f"LLM returned invalid JSON. Parse error: {e}. "
                f"Raw output (first 300 chars): {raw_response[:300]}"
            )

    def _validate_schema(self, extracted_dict: dict) -> JDExtractionResult:
        """
        Validates the parsed dictionary against the Pydantic JDExtractionResult schema.
        If the LLM drops a required field or returns the wrong type, Pydantic raises
        a descriptive ValidationError returned as a 422 response.
        """
        try:
            return JDExtractionResult(**extracted_dict)
        except Exception as e:
            logger.error(f"Pydantic validation failed: {e}")
            raise ValueError(f"Extracted data failed schema validation: {e}")
