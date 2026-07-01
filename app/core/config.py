from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = 'gemini-2.5-flash'
    SIMILARITY_THRESHOLD: float = 0.65
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 4096
    CANDIDATES_FILE: str = 'data/sample_candidates.json'
    SHORTLIST_SIZE: int = 10
    APP_TITLE: str = 'AI Recruiter — Candidate Ranking Intelligence'
    APP_DESCRIPTION: str = 'End-to-end AI recruiter pipeline: Transforms raw Job Description text into structured signals, then ranks candidates the way a great recruiter would — understanding who actually fits, not just matching keywords.'
    APP_VERSION: str = '2.0.0'
    ALLOWED_ORIGINS: list[str] = ['http://localhost:3000', 'http://localhost:5173', '*']

    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

@lru_cache()
def get_settings() -> Settings:
    return Settings()