"""
Pydantic models for Phase 2: Candidate Ranking Engine.

These models define the request/response contract for the ranking pipeline.
They are designed to directly consume JDExtractionResult from Phase 1.
"""

from pydantic import BaseModel, Field
from typing import Optional
from sentence_transformers import SentenceTransformer, util
import hashlib
import re


# ─────────────────────────────────────────────────────────────
# CANDIDATE DATA MODELS (mirrors sample_candidates.json schema)
# ─────────────────────────────────────────────────────────────

class CandidateSkill(BaseModel):
    name: str
    proficiency: Optional[str] = None          # "expert", "advanced", "intermediate", "beginner"
    years: Optional[float] = None


class CareerEntry(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    duration_months: Optional[int] = None
    company_type: Optional[str] = None         # "product", "consulting", "startup", "FAANG"
    company_size: Optional[str] = None         # "startup", "mid", "large", "enterprise"


class RedrobSignals(BaseModel):
    """Platform-specific behavioral signals from the Redrob dataset."""
    open_to_work_flag: Optional[bool] = None
    profile_completeness_score: Optional[float] = None   # 0.0 – 1.0
    recruiter_response_rate: Optional[float] = None      # 0.0 – 1.0
    interview_completion_rate: Optional[float] = None    # 0.0 – 1.0
    notice_period_days: Optional[int] = None
    last_active_days_ago: Optional[int] = None


class CandidateProfile(BaseModel):
    years_of_experience: Optional[float] = None
    location: Optional[str] = None
    willing_to_relocate: Optional[bool] = False
    current_industry: Optional[str] = None
    education_tier: Optional[str] = None       # "tier1", "tier2", "other"


class Candidate(BaseModel):
    """
    Full candidate record as it appears in sample_candidates.json.
    All fields are Optional to handle real-world data quality issues.
    """
    candidate_id: str
    name: str
    profile: Optional[CandidateProfile] = None
    skills: Optional[list[CandidateSkill]] = []
    career_history: Optional[list[CareerEntry]] = []
    skill_embeddings: Optional[list[float]] = None  # List of embedding vectors for candidate skills
    summary: Optional[str] = None              # Free-text professional summary
    redrob_signals: Optional[RedrobSignals] = None

    def _extract_years_regex(self, text: str) -> int | None:
        """Extract years of experience from free‑text using a simple regex.
        Returns integer years or None if not found.
        """
        match = re.search(r"(\d+)\s+years?", text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None


# ─────────────────────────────────────────────────────────────
# RANKING REQUEST / RESPONSE MODELS
# ─────────────────────────────────────────────────────────────

class RankingRequest(BaseModel):
    """
    Request body for the /api/rank-candidates endpoint.
    Accepts candidates as JSON — the JD extraction is run internally.
    """
    raw_jd_text: str = Field(
        ...,
        min_length=50,
        description="Raw job description text. Will be extracted then used to rank candidates."
    )
    candidates: list[Candidate] = Field(
        ...,
        description="List of candidate objects to rank."
    )
    shortlist_size: Optional[int] = Field(
        default=10,
        ge=1,
        le=50,
        description="How many top candidates to include in the shortlist."
    )


class ScoreBreakdown(BaseModel):
    """Transparent score breakdown so recruiters understand WHY a candidate ranked."""
    must_have_skills_score: float = Field(description="0-40 points: core skill match")
    experience_score: float = Field(description="0-20 points: years of experience fit")
    nice_to_have_score: float = Field(description="0-15 points: bonus skill coverage")
    behavioral_score: float = Field(description="0-10 points: redrob platform signals")
    location_score: float = Field(description="0-10 points: location / availability fit")
    notice_period_score: float = Field(description="0-5 points: availability speed")
    disqualifier_penalty: float = Field(description="Negative: penalty for disqualifiers hit")
    total_score: float = Field(description="Final score (max 100, may go negative with penalties)")


class RankedCandidate(BaseModel):
    """A single candidate in the ranked shortlist."""
    rank: int
    candidate_id: str
    name: str
    total_score: float
    score_breakdown: ScoreBreakdown
    matched_must_have_skills: list[str] = Field(description="Must-have skills this candidate has")
    missing_must_have_skills: list[str] = Field(description="Must-have skills this candidate lacks")
    matched_nice_to_have: list[str] = Field(description="Nice-to-have skills matched")
    disqualifiers_hit: list[str] = Field(description="Disqualifiers that apply to this candidate")
    recruiter_note: str = Field(description="1-2 sentence human-readable summary for the recruiter")


class RankingResponse(BaseModel):
    """Full response from the ranking pipeline."""
    job_title: str
    total_candidates_evaluated: int
    shortlist: list[RankedCandidate]
    disqualified_count: int = Field(description="Candidates removed due to hard disqualifiers")
    extraction_confidence: str
    ranking_metadata: dict = Field(description="Weights and config used for this ranking run")
