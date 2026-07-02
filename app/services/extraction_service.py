import json
import hashlib
import logging
import asyncio
from google import genai
from google.genai import types
from app.core.config import get_settings
from app.models.jd_models import JDExtractionResult
logger = logging.getLogger(__name__)
_jd_cache: dict[str, JDExtractionResult] = {}
SYSTEM_PROMPT = """
You are an expert Technical Recruiter and Signal Extraction System.
Parse the Job Description and return a structured JSON object with ALL hiring signals.

CRITICAL RULES FOR SKILLS EXTRACTION:
1. You MUST return ONLY a valid JSON object. No markdown, no prose, no explanation.
2. SKILLS MUST BE ATOMIC — each skill entry must be ONE specific technology, tool, or concept.
   BAD:  "Deep technical depth in modern ML systems (embeddings, retrieval, ranking, LLMs, fine-tuning)"
   GOOD: ["embeddings", "retrieval systems", "LLMs", "fine-tuning", "ranking algorithms"]
   BAD:  "Production experience with vector databases (FAISS, Pinecone)"
   GOOD: ["FAISS", "Pinecone", "vector databases", "production ML deployment"]
3. must_have_skills: List 8-15 INDIVIDUAL atomic skills. These are non-negotiable — absence = reject.
   Split any combined phrases into multiple separate skill entries.
4. nice_to_have_skills: List 5-10 INDIVIDUAL atomic preferred skills. Not blockers but differentiate candidates.
5. disqualifiers: List 3-8 specific red flags or anti-patterns that would eliminate a candidate.
   Examples: "only consulting firm background (TCS/Infosys/Wipro)", "no production ML deployment experience",
   "computer vision specialist without NLP", "pure academic researcher with no industry work".
   NEVER leave this empty if the JD has any implicit or explicit exclusions.
6. For minimum_years_experience: use the LOWER bound of any range. NEVER return null — use 0 if unknown.
7. behavioral_traits: Extract 3-6 culture/work-style signals (implicit or explicit).
8. remote_ok: true ONLY if JD explicitly says remote/WFH is OK.
9. extraction_confidence: "high" if JD is detailed (>500 words), "medium" if moderate, "low" if vague.

OUTPUT JSON SCHEMA (return EXACTLY this structure, no extra fields):
{
  "job_title": "<string>",
  "minimum_years_experience": <integer, never null, use 0 if unknown>,
  "maximum_years_experience": <integer or null>,
  "must_have_skills": ["<atomic skill>", "<atomic skill>", ...],
  "nice_to_have_skills": ["<atomic skill>", ...],
  "behavioral_traits": ["<trait>", ...],
  "domain_knowledge": ["<domain>", ...],
  "disqualifiers": ["<specific disqualifier>", ...],
  "preferred_locations": ["<city>", ...],
  "remote_ok": <boolean>,
  "preferred_notice_period_days": <integer or null>,
  "preferred_company_types": ["<type>", ...],
  "key_responsibilities_summary": "<2-3 sentence summary of day-to-day work>",
  "extraction_confidence": "<high|medium|low>"
}
"""

class JDExtractionService:
    # Models to try in order. gemini-1.5-flash removed (404 in v1beta).
    FALLBACK_MODELS = ['gemini-2.5-flash', 'gemini-2.0-flash-lite', 'gemini-2.0-flash', 'gemini-2.5-pro']
    # Retry waits per attempt — kept short so we stay within HTTP request timeout
    RETRY_WAITS = [5, 10, 15]
    # Cooldown between model switches when all retries were rate-limited
    MODEL_SWITCH_COOLDOWN = 5

    def __init__(self):
        self.settings = get_settings()
        self.client = genai.Client(api_key=self.settings.GEMINI_API_KEY)
        logger.info(f'JDExtractionService initialized | model={self.settings.GEMINI_MODEL}')

    async def extract(self, raw_jd_text: str) -> JDExtractionResult:
        cache_key = hashlib.md5(raw_jd_text.strip().encode()).hexdigest()
        if cache_key in _jd_cache:
            logger.info(f'Cache HIT for JD (md5={cache_key[:8]}...) — skipping Gemini call')
            return _jd_cache[cache_key]
        logger.info(f'Cache MISS | Starting JD extraction | text_length={len(raw_jd_text)}')
        raw_response = await self._call_gemini(raw_jd_text)
        extracted_dict = self._parse_json_response(raw_response)
        validated_result = self._validate_schema(extracted_dict)
        _jd_cache[cache_key] = validated_result
        logger.info(f"Extraction complete | job_title='{validated_result.job_title}' | must_have_count={len(validated_result.must_have_skills)} | confidence={validated_result.extraction_confidence}")
        return validated_result

    async def _call_gemini(self, raw_jd_text: str) -> str:
        user_message = (
            f'Extract all hiring signals from this Job Description:\n\n'
            f'---BEGIN JD---\n{raw_jd_text}\n---END JD---\n\n'
            f'Return ONLY a valid JSON object matching the schema. No markdown, no prose.'
        )
        # NOTE: Do NOT use response_mime_type='application/json' — it restricts output token length
        # and causes truncated responses. We parse the text output ourselves.
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=self.settings.LLM_TEMPERATURE,
            max_output_tokens=self.settings.LLM_MAX_TOKENS,
        )
        primary = self.settings.GEMINI_MODEL
        models_to_try = [primary] + [m for m in self.FALLBACK_MODELS if m != primary]
        last_error = None

        for model_idx, model in enumerate(models_to_try):
            for attempt in range(1, len(self.RETRY_WAITS) + 2):  # 1..4
                try:
                    logger.info(f'Gemini call | model={model} | attempt={attempt}')
                    response = await self.client.aio.models.generate_content(
                        model=model, contents=user_message, config=config
                    )
                    raw_content = response.text
                    if not raw_content or not raw_content.strip():
                        raise ValueError(f'Gemini returned empty response for model={model}')
                    logger.info(f'Gemini success | model={model} | response_len={len(raw_content)}')
                    return raw_content
                except asyncio.CancelledError:
                    # Must propagate — this means the HTTP request was cancelled/timed out
                    logger.warning('Request cancelled during Gemini call')
                    raise
                except Exception as e:
                    err_str = str(e)
                    last_error = e
                    is_rate_limited = '429' in err_str or 'RESOURCE_EXHAUSTED' in err_str
                    is_unavailable = '503' in err_str or 'UNAVAILABLE' in err_str
                    is_retryable = is_rate_limited or is_unavailable

                    if is_retryable:
                        attempt_idx = attempt - 1
                        if attempt_idx < len(self.RETRY_WAITS):
                            wait = self.RETRY_WAITS[attempt_idx]
                            logger.warning(
                                f'Gemini {err_str[:80]}... | model={model} | attempt={attempt} | retrying in {wait}s'
                            )
                            try:
                                await asyncio.sleep(wait)
                            except asyncio.CancelledError:
                                logger.warning('Sleep cancelled — request timed out')
                                raise
                            continue
                        else:
                            logger.warning(f'All retries exhausted for model={model}, trying fallback')
                            if model_idx < len(models_to_try) - 1:
                                logger.info(f'Cooldown {self.MODEL_SWITCH_COOLDOWN}s before switching model')
                                try:
                                    await asyncio.sleep(self.MODEL_SWITCH_COOLDOWN)
                                except asyncio.CancelledError:
                                    raise
                            break
                    else:
                        logger.warning(
                            f'Gemini non-retryable error ({err_str[:80]}) for model={model}, trying fallback'
                        )
                        break

        raise RuntimeError(
            f'Gemini unavailable across all fallback models. Last error: {last_error}'
        )


    def _repair_truncated_json(self, text: str) -> str:
        """Attempt to close truncated JSON by balancing open brackets/braces.
        Handles the common case where Gemini cuts off mid-string due to token limits.
        """
        # If we're inside an unterminated string, close it first
        # Count unescaped quotes to detect open string state
        in_string = False
        escape_next = False
        for ch in text:
            if escape_next:
                escape_next = False
                continue
            if ch == '\\':
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string

        repaired = text
        if in_string:
            # Trim back to last complete value by finding the last comma or opening bracket
            # Then close the string
            repaired = text.rstrip()
            # Remove the dangling incomplete string value
            last_safe = max(repaired.rfind(','), repaired.rfind('['), repaired.rfind('{'))
            if last_safe > 0:
                repaired = repaired[:last_safe]
            else:
                repaired += '"'  # just close the string as last resort

        # Now balance brackets and braces
        stack = []
        in_str = False
        esc = False
        for ch in repaired:
            if esc:
                esc = False
                continue
            if ch == '\\':
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if not in_str:
                if ch in '{[':
                    stack.append('}' if ch == '{' else ']')
                elif ch in '}]' and stack:
                    stack.pop()

        # Append closers in reverse order
        closing = ''.join(reversed(stack))
        return repaired + closing

    def _parse_json_response(self, raw_response: str) -> dict:
        def _try_parse(text: str) -> dict:
            cleaned = text.strip()
            # Strip markdown code fences (```json ... ``` or ``` ... ```)
            if cleaned.startswith('```'):
                lines = cleaned.split('\n')
                inner_lines = lines[1:]
                if inner_lines and inner_lines[-1].strip() == '```':
                    inner_lines = inner_lines[:-1]
                cleaned = '\n'.join(inner_lines).strip()
            return json.loads(cleaned)

        # First attempt: parse as-is
        try:
            return _try_parse(raw_response)
        except json.JSONDecodeError as e:
            logger.warning(f'JSON parse failed (likely truncated) — attempting repair | error={e}')

        # Second attempt: repair truncated JSON
        try:
            repaired = self._repair_truncated_json(raw_response.strip())
            result = _try_parse(repaired)
            logger.info('JSON repair succeeded — truncated response was recovered')
            return result
        except json.JSONDecodeError as e2:
            pos = e2.pos
            start = max(0, pos - 100)
            end = min(len(raw_response), pos + 100)
            context = raw_response[start:end]
            logger.error(f"JSON parse failed even after repair | error={e2} | context='{context}' | raw={raw_response[:500]}")
            raise ValueError(f'LLM returned invalid JSON. Parse error: {e2}. Context: ... {context} ...')


    def _sanitize_dict(self, d: dict) -> dict:
        """Apply safe defaults so Pydantic never fails on missing/null required fields."""
        def to_list(val):
            if val is None:
                return []
            if isinstance(val, list):
                return [str(i) for i in val if i is not None]
            return [str(val)]

        def to_int(val, default=0):
            if val is None:
                return default
            try:
                return max(0, int(val))
            except (ValueError, TypeError):
                return default

        return {
            'job_title': str(d.get('job_title') or 'Unknown Position').strip() or 'Unknown Position',
            'minimum_years_experience': to_int(d.get('minimum_years_experience'), 0),
            'maximum_years_experience': to_int(d.get('maximum_years_experience')) if d.get('maximum_years_experience') is not None else None,
            'must_have_skills': to_list(d.get('must_have_skills')),
            'nice_to_have_skills': to_list(d.get('nice_to_have_skills')),
            'behavioral_traits': to_list(d.get('behavioral_traits')),
            'domain_knowledge': to_list(d.get('domain_knowledge')),
            'disqualifiers': to_list(d.get('disqualifiers')),
            'preferred_locations': to_list(d.get('preferred_locations')),
            'remote_ok': bool(d.get('remote_ok', False)),
            'preferred_notice_period_days': to_int(d.get('preferred_notice_period_days')) if d.get('preferred_notice_period_days') is not None else None,
            'preferred_company_types': to_list(d.get('preferred_company_types')),
            'key_responsibilities_summary': str(d.get('key_responsibilities_summary') or 'No summary provided.').strip() or 'No summary provided.',
            'extraction_confidence': str(d.get('extraction_confidence') or 'medium').lower(),
        }

    def _validate_schema(self, extracted_dict: dict) -> JDExtractionResult:
        try:
            sanitized = self._sanitize_dict(extracted_dict)
            return JDExtractionResult(**sanitized)
        except Exception as e:
            logger.error(f'Pydantic validation failed even after sanitization: {e}')
            raise ValueError(f'Extracted data failed schema validation: {e}')