from pydantic import BaseModel, Field, model_validator
from typing import Optional
from sentence_transformers import SentenceTransformer, util
import hashlib
import re
from datetime import datetime

class CandidateSkill(BaseModel):
    name: str
    proficiency: Optional[str] = None
    years: Optional[float] = None

    @model_validator(mode='before')
    @classmethod
    def map_duration_to_years(cls, data):
        if isinstance(data, dict):
            if data.get('years') is None and data.get('duration_months') is not None:
                try:
                    data['years'] = round(float(data['duration_months']) / 12.0, 2)
                except Exception:
                    pass
        return data

class CareerEntry(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    duration_months: Optional[int] = None
    company_type: Optional[str] = None
    company_size: Optional[str] = None

class RedrobSignals(BaseModel):
    open_to_work_flag: Optional[bool] = None
    profile_completeness_score: Optional[float] = None
    recruiter_response_rate: Optional[float] = None
    interview_completion_rate: Optional[float] = None
    notice_period_days: Optional[int] = None
    last_active_days_ago: Optional[int] = None

    @model_validator(mode='before')
    @classmethod
    def calculate_active_days(cls, data):
        if isinstance(data, dict):
            if data.get('last_active_days_ago') is None:
                active_date_str = data.get('last_active_date')
                if active_date_str:
                    try:
                        active_date = datetime.strptime(active_date_str, '%Y-%m-%d').date()
                        today = datetime(2026, 7, 1).date()
                        data['last_active_days_ago'] = max(0, (today - active_date).days)
                    except Exception:
                        pass
        return data

class CandidateProfile(BaseModel):
    years_of_experience: Optional[float] = None
    location: Optional[str] = None
    willing_to_relocate: Optional[bool] = False
    current_industry: Optional[str] = None
    education_tier: Optional[str] = None

class Candidate(BaseModel):
    candidate_id: str
    name: str
    profile: Optional[CandidateProfile] = None
    skills: Optional[list[CandidateSkill]] = []
    career_history: Optional[list[CareerEntry]] = []
    skill_embeddings: Optional[list[float]] = None
    summary: Optional[str] = None
    redrob_signals: Optional[RedrobSignals] = None

    @model_validator(mode='before')
    @classmethod
    def normalize_candidate(cls, data):
        if isinstance(data, dict):
            if not data.get('name'):
                profile = data.get('profile')
                if isinstance(profile, dict):
                    data['name'] = profile.get('anonymized_name') or profile.get('name')
            if not data.get('name'):
                data['name'] = 'Unknown Candidate'
            profile = data.get('profile')
            signals = data.get('redrob_signals')
            if isinstance(profile, dict) and isinstance(signals, dict):
                if 'willing_to_relocate' not in profile and 'willing_to_relocate' in signals:
                    profile['willing_to_relocate'] = signals['willing_to_relocate']
            if isinstance(profile, dict) and 'education_tier' not in profile:
                edu_list = data.get('education')
                if isinstance(edu_list, list) and len(edu_list) > 0:
                    first_edu = edu_list[0]
                    if isinstance(first_edu, dict) and 'tier' in first_edu:
                        profile['education_tier'] = first_edu['tier']
        return data

    def _extract_years_regex(self, text: str) -> int | None:
        match = re.search('(\\d+)\\s+years?', text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None

class RankingRequest(BaseModel):
    raw_jd_text: str = Field(..., min_length=50, description='Raw job description text. Will be extracted then used to rank candidates.')
    candidates: list[Candidate] = Field(..., description='List of candidate objects to rank.')
    shortlist_size: Optional[int] = Field(default=10, ge=1, le=10000, description='How many top candidates to include in the shortlist.')

class ScoreBreakdown(BaseModel):
    must_have_skills_score: float = Field(description='0-40 points: core skill match')
    experience_score: float = Field(description='0-20 points: years of experience fit')
    nice_to_have_score: float = Field(description='0-15 points: bonus skill coverage')
    behavioral_score: float = Field(description='0-10 points: redrob platform signals')
    location_score: float = Field(description='0-10 points: location / availability fit')
    notice_period_score: float = Field(description='0-5 points: availability speed')
    disqualifier_penalty: float = Field(description='Negative: penalty for disqualifiers hit')
    total_score: float = Field(description='Final score (max 100, may go negative with penalties)')

class RankedCandidate(BaseModel):
    rank: int
    candidate_id: str
    name: str
    total_score: float
    score_breakdown: ScoreBreakdown
    matched_must_have_skills: list[str] = Field(description='Must-have skills this candidate has')
    missing_must_have_skills: list[str] = Field(description='Must-have skills this candidate lacks')
    matched_nice_to_have: list[str] = Field(description='Nice-to-have skills matched')
    disqualifiers_hit: list[str] = Field(description='Disqualifiers that apply to this candidate')
    recruiter_note: str = Field(description='1-2 sentence human-readable summary for the recruiter')

class RankingResponse(BaseModel):
    job_title: str
    total_candidates_evaluated: int
    shortlist: list[RankedCandidate]
    disqualified_count: int = Field(description='Candidates removed due to hard disqualifiers')
    extraction_confidence: str
    ranking_metadata: dict = Field(description='Weights and config used for this ranking run')