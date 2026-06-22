"""
Core configuration module for the JD Extractor microservice.

Uses Pydantic Settings to load and validate environment variables.
This ensures fail-fast behaviour if the API key is not set.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings — loaded from .env file or environment variables."""

    # ── Groq API ──────────────────────────────────────────────
    GROQ_API_KEY: str

    # ── Model Configuration ───────────────────────────────────
    # llama-3.3-70b-versatile: best reasoning for structured extraction.
    # llama-3.1-8b-instant: ~5× faster, sufficient for extraction.
    GROQ_MODEL: str = "llama-3.1-8b-instant"

    # Low temperature keeps extraction deterministic and factual.
    LLM_TEMPERATURE: float = 0.05

    # Maximum tokens for the LLM response. The JSON output should
    # always fit comfortably within 1024 tokens.
    LLM_MAX_TOKENS: int = 1200

    # ── Ranking Configuration ─────────────────────────────────
    # Path to the candidates JSON dataset (relative to project root)
    CANDIDATES_FILE: str = "data/sample_candidates.json"

    # Number of candidates to include in the shortlist
    SHORTLIST_SIZE: int = 10

    # ── App Configuration ─────────────────────────────────────
    APP_TITLE: str = "AI Recruiter — JD Intelligence + Candidate Ranking"
    APP_DESCRIPTION: str = (
        "End-to-end AI recruiter pipeline: Transforms raw Job Description text into "
        "structured signals, then ranks candidates the way a great recruiter would — "
        "understanding who actually fits, not just matching keywords."
    )
    APP_VERSION: str = "2.0.0"

    # ── CORS Configuration (for React frontend) ───────────────
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173", "*"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """
    Cached settings loader. lru_cache ensures .env is only read once
    per process lifetime — important for performance in async contexts.
    """
    return Settings()
