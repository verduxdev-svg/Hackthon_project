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
SYSTEM_PROMPT = '\nYou are an expert Technical Recruiter and Intelligence Extraction System.\nYour task is to parse a raw Job Description (JD) and extract ALL meaningful\nhiring signals into a structured JSON object.\n\nCRITICAL RULES:\n1. You MUST return ONLY a valid JSON object. No explanations, no markdown, no prose.\n2. Extract skills into TWO distinct categories:\n   - must_have_skills: Non-negotiable. Absence = candidate should be rejected.\n   - nice_to_have_skills: Preferred but not blockers.\n3. For minimum_years_experience: if a range is given (e.g., "5-9 years"),\n   use the LOWER bound as an integer. NEVER return null — use 0 if unknown.\n4. Behavioral traits: Look for culture/work-style signals (e.g., "bias for action",\n   "async-first", "comfortable with ambiguity"). These are often implicit.\n5. Disqualifiers: Extract EXPLICIT anti-patterns mentioned in the JD\n   (e.g., "no consulting-only backgrounds", "no pure research roles").\n6. Domain knowledge: Areas of expertise beyond named technologies.\n7. preferred_company_types: If the JD mentions preferring or penalizing certain company types.\n8. remote_ok: Set to true only if the JD explicitly says remote or WFH is OK.\n9. extraction_confidence: Set to "high" if the JD is detailed, "medium" if ambiguous, "low" if vague.\n\nOUTPUT JSON SCHEMA (return EXACTLY this structure):\n{\n  "job_title": "<string>",\n  "minimum_years_experience": <integer, never null, use 0 if unknown>,\n  "maximum_years_experience": <integer or null>,\n  "must_have_skills": ["<string>", ...],\n  "nice_to_have_skills": ["<string>", ...],\n  "behavioral_traits": ["<string>", ...],\n  "domain_knowledge": ["<string>", ...],\n  "disqualifiers": ["<string>", ...],\n  "preferred_locations": ["<string>", ...],\n  "remote_ok": <boolean>,\n  "preferred_notice_period_days": <integer or null>,\n  "preferred_company_types": ["<string>", ...],\n  "key_responsibilities_summary": "<2-3 sentence summary>",\n  "extraction_confidence": "<high|medium|low>"\n}\n'

class JDExtractionService:
    FALLBACK_MODELS = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-2.5-pro']

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
        logger.info(f"Extraction complete | job_title='{validated_result.job_title}' | must_have_count={len(validated_result.must_have_skills)} | disqualifiers_count={len(validated_result.disqualifiers)} | confidence={validated_result.extraction_confidence}")
        return validated_result

    async def _call_gemini(self, raw_jd_text: str) -> str:
        user_message = f'Extract all hiring signals from this Job Description:\n\n---BEGIN JD---\n{raw_jd_text}\n---END JD---\n\nReturn ONLY a valid JSON object matching the schema. No markdown, no prose.'
        config = types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, temperature=self.settings.LLM_TEMPERATURE, max_output_tokens=self.settings.LLM_MAX_TOKENS, response_mime_type='application/json')
        primary = self.settings.GEMINI_MODEL
        models_to_try = [primary] + [m for m in self.FALLBACK_MODELS if m != primary]
        last_error = None
        for model in models_to_try:
            for attempt in range(1, 4):
                try:
                    logger.info(f'Gemini call | model={model} | attempt={attempt}')
                    response = await self.client.aio.models.generate_content(model=model, contents=user_message, config=config)
                    raw_content = response.text
                    logger.debug(f'Gemini response: {raw_content[:200]}...')
                    logger.info(f'Gemini success | model={model}')
                    return raw_content
                except Exception as e:
                    err_str = str(e)
                    last_error = e
                    is_retryable = '503' in err_str or 'UNAVAILABLE' in err_str or '429' in err_str or ('RESOURCE_EXHAUSTED' in err_str)
                    if is_retryable:
                        if attempt < 3:
                            wait = 5 * attempt
                            logger.warning(f'Gemini {err_str[:80]}... | model={model} | attempt={attempt} | retrying in {wait}s')
                            await asyncio.sleep(wait)
                            continue
                        else:
                            logger.warning(f'All retries exhausted for model={model}, trying fallback')
                            break
                    else:
                        logger.warning(f'Gemini non-retryable error ({err_str[:80]}) for model={model}, trying fallback')
                        break
        raise RuntimeError(f'Gemini unavailable across all fallback models. Last error: {last_error}')

    def _parse_json_response(self, raw_response: str) -> dict:
        try:
            cleaned = raw_response.strip()
            if cleaned.startswith('```'):
                lines = cleaned.split('\n')
                cleaned = '\n'.join(lines[1:-1])
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            pos = e.pos
            start = max(0, pos - 100)
            end = min(len(raw_response), pos + 100)
            context = raw_response[start:end]
            logger.error(f"JSON parse failed | error={e} | context_around_error='{context}' | raw={raw_response}")
            raise ValueError(f'LLM returned invalid JSON. Parse error: {e}. Context: ... {context} ...')

    def _validate_schema(self, extracted_dict: dict) -> JDExtractionResult:
        try:
            return JDExtractionResult(**extracted_dict)
        except Exception as e:
            logger.error(f'Pydantic validation failed: {e}')
            raise ValueError(f'Extracted data failed schema validation: {e}')