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
    # llama-3.3-70b-versatile is the current production-ready 70B model on Groq.
    # It has the best reasoning for structured extraction tasks.
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Low temperature keeps extraction deterministic and factual.
    LLM_TEMPERATURE: float = 0.05

    # Maximum tokens for the LLM response. The JSON output should
    # always fit comfortably within 1024 tokens.
    LLM_MAX_TOKENS: int = 1500

    # ── App Configuration ─────────────────────────────────────
    APP_TITLE: str = "Phase 1: AI Recruiter — JD Intelligence Extractor"
    APP_DESCRIPTION: str = (
        "Transforms raw, noisy Job Description text into a clean, "
        "validated JSON object ready for Phase 2 candidate ranking."
    )
    APP_VERSION: str = "1.0.0"

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
