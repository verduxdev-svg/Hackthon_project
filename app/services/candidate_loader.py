"""
Candidate Loader Service

Loads and validates the candidate dataset (sample_candidates.json) from disk.
Cached in app state at startup — zero per-request I/O overhead.
"""

import json
import logging
from pathlib import Path

from app.core.config import get_settings
from app.models.ranking_models import Candidate

logger = logging.getLogger(__name__)


class CandidateLoaderService:
    """
    Loads candidates from disk on startup and caches them in memory.
    Thread-safe for concurrent reads (immutable after load).
    """

    def __init__(self):
        self.settings = get_settings()
        self._candidates: list[Candidate] = []
        self._loaded = False

    def load(self) -> list[Candidate]:
        """
        Load candidates from CANDIDATES_FILE path.
        Returns empty list if file doesn't exist (graceful degradation).
        """
        if self._loaded:
            return self._candidates

        candidates_path = Path(self.settings.CANDIDATES_FILE)

        if not candidates_path.exists():
            logger.warning(
                f"Candidates file not found at '{candidates_path}'. "
                f"POST /api/rank-candidates will still work with inline candidate data."
            )
            self._loaded = True
            return []

        try:
            raw = candidates_path.read_text(encoding="utf-8")
            data = json.loads(raw)

            # Support both {"candidates": [...]} and [...] top-level formats
            if isinstance(data, dict):
                data = data.get("candidates", data.get("data", []))

            self._candidates = [Candidate(**c) for c in data]
            self._loaded = True
            logger.info(
                f"Loaded {len(self._candidates)} candidates from '{candidates_path}'"
            )
            return self._candidates

        except Exception as e:
            logger.error(f"Failed to load candidates from '{candidates_path}': {e}")
            self._loaded = True
            return []

    def get_candidates(self) -> list[Candidate]:
        """Returns the cached candidate list."""
        if not self._loaded:
            return self.load()
        return self._candidates

    def count(self) -> int:
        return len(self.get_candidates())
