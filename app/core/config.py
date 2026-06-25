"""
Core configuration module for the AI Recruiter microservice.

Uses Pydantic Settings to load and validate environment variables.
This ensures fail-fast behaviour if the API key is not set.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings — loaded from .env file or environment variables."""

    # ── Google Gemini API ──────────────────────────────────────
    GEMINI_API_KEY: str

    # ── Model Configuration ───────────────────────────────────
    GEMINI_MODEL: str = "gemini-2.5-flash"
    SIMILARITY_THRESHOLD: float = 0.65  # Cosine similarity cutoff for semantic skill matching

    # Low temperature keeps extraction deterministic and factual.
    LLM_TEMPERATURE: float = 0.1

    # Maximum tokens for the LLM response.
    LLM_MAX_TOKENS: int = 4096

    # ── Ranking Configuration ─────────────────────────────────
    # Path to the candidates JSON dataset (relative to project root)
    CANDIDATES_FILE: str = "data/sample_candidates.json"

    # Number of candidates to include in the shortlist
    SHORTLIST_SIZE: int = 10

    # ── App Configuration ─────────────────────────────────────
    APP_TITLE: str = "AI Recruiter — Candidate Ranking Intelligence"
    APP_DESCRIPTION: str = (
        "End-to-end AI recruiter pipeline: Transforms raw Job Description text into "
        "structured signals, then ranks candidates the way a great recruiter would — "
        "understanding who actually fits, not just matching keywords."
    )
    APP_VERSION: str = "2.0.0"

    # ── CORS Configuration ────────────────────────────────────
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
