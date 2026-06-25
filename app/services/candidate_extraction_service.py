"""
Candidate Extraction Service.
Powered by Google Gemini (google-genai SDK).

Extracts structured candidate data from raw resume text.
"""

import json
import logging
import uuid
import asyncio
import hashlib
import re
from google import genai
from google.genai import types

from app.core.config import get_settings
from app.models.candidate_models import Candidate

logger = logging.getLogger(__name__)

# In‑process cache for resume extraction
_candidate_cache: dict[str, Candidate] = {}

SYSTEM_PROMPT = """
You are an expert Technical Recruiter parsing a candidate resume.
Extract ALL relevant information into a structured JSON object.

CRITICAL RULES:
1. Return ONLY a valid JSON object. No markdown, no prose, no explanations.
2. years_of_experience: total professional experience as an integer. Use 0 if unclear.
3. skills: all technical skills, tools, frameworks mentioned.
4. current_location: city/country if mentioned, else null.
5. notice_period_days: integer if stated, else null.

OUTPUT JSON SCHEMA:
{
  "name": "<string>",
  "email": "<string or null>",
  "years_of_experience": <integer>,
  "skills": ["<string>", ...],
  "past_companies": ["<string>", ...],
  "education": ["<string>", ...],
  "current_location": "<string or null>",
  "notice_period_days": <integer or null>,
  "achievements": ["<string>", ...],
  "summary": "<2-3 sentence professional summary>"
}
"""


class CandidateExtractionService:
    FALLBACK_MODELS = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    ]

    def __init__(self):
        self.settings = get_settings()
        self.client = genai.Client(api_key=self.settings.GEMINI_API_KEY)
        logger.info(f"CandidateExtractionService initialized | model={self.settings.GEMINI_MODEL}")

    async def extract(self, raw_resume_text: str) -> Candidate:
        # Compute MD5 hash of the raw text for caching
        cache_key = hashlib.md5(raw_resume_text.encode('utf-8')).hexdigest()
        if cache_key in _candidate_cache:
            logger.info("Resume extraction cache hit")
            return _candidate_cache[cache_key]

        if len(raw_resume_text.strip()) < 50:
            raise ValueError("Resume text is too short to extract meaningful information.")

        logger.info("Calling Gemini API for candidate resume extraction...")

        primary = self.settings.GEMINI_MODEL
        models_to_try = [primary] + [m for m in self.FALLBACK_MODELS if m != primary]
        last_error = None

        for model in models_to_try:
            for attempt in range(1, 4):
                try:
                    logger.info(f"Gemini candidate call | model={model} | attempt={attempt}")
                    response = await self.client.aio.models.generate_content(
                        model=model,
                        contents=f"Extract the following resume:\n\n{raw_resume_text}\n\nReturn ONLY valid JSON.",
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_PROMPT,
                            temperature=0.0,
                            max_output_tokens=4096,
                            response_mime_type="application/json",
                        ),
                    )

                    response_content = response.text
                    if not response_content:
                        raise ValueError("Gemini returned an empty response.")

                    parsed_data = json.loads(response_content)
                    # Regex fallback for years of experience if missing or zero
                    if not parsed_data.get('years_of_experience') or parsed_data.get('years_of_experience') == 0:
                        # Simple regex to capture "X years" patterns
                        match = re.search(r"(\d+)\s+years?", raw_resume_text, re.IGNORECASE)
                        if match:
                            parsed_data['years_of_experience'] = int(match.group(1))
                    parsed_data["candidate_id"] = f"C_{uuid.uuid4().hex[:8]}"
                    candidate = Candidate(**parsed_data)
                    logger.info(f"Successfully extracted candidate: {candidate.name}")
                    # Store in cache
                    _candidate_cache[cache_key] = candidate
                    return candidate

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse Gemini JSON output: {e}")
                    raise ValueError("Gemini output was not valid JSON.")

                except Exception as e:
                    err_str = str(e)
                    last_error = e
                    is_retryable = ("503" in err_str or "UNAVAILABLE" in err_str
                                    or "429" in err_str or "RESOURCE_EXHAUSTED" in err_str)

                    if is_retryable and attempt < 3:
                        wait = 2 ** attempt
                        logger.warning(f"Retrying candidate extraction | model={model} | wait={wait}s")
                        await asyncio.sleep(wait)
                        continue

                    if is_retryable:
                        logger.warning(f"Fallback: exhausted retries for model={model}")
                        break

                    logger.error(f"Candidate extraction non-retryable error: {e}")
                    raise RuntimeError(f"Extraction failed: {e}")

        raise RuntimeError(f"Gemini unavailable for candidate extraction. Last error: {last_error}")
