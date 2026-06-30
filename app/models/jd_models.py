"""
Pydantic models for Phase 1: JD Extraction Microservice.

These models define the strict JSON contract for both incoming requests
and outgoing validated extraction results. Pydantic enforces the schema
at runtime — if the LLM produces bad output, we catch it here.
"""

from pydantic import BaseModel, Field, validator
from typing import Optional


# ─────────────────────────────────────────────────────────────
# REQUEST MODEL
# ─────────────────────────────────────────────────────────────

class JDRequest(BaseModel):
    """The raw job description text sent by the client."""
    raw_jd_text: str = Field(
        ...,
        min_length=50,
        description="The raw, unstructured job description text to be parsed.",
        example=(
            "We are hiring a Senior Machine Learning Engineer with 5+ years of "
            "experience in Python, PyTorch, and production deployment of ML models..."
        )
    )


# ─────────────────────────────────────────────────────────────
# RESPONSE MODEL — The Core JD Extraction Schema
# ─────────────────────────────────────────────────────────────

class JDExtractionResult(BaseModel):
    """
    Validated, structured output from the JD extraction pipeline.

    This is the canonical schema that Phase 2 (scoring/ranking) will consume.
    Every field has been designed to directly map to signals in the candidate
    dataset (sample_candidates.json).
    """

    # ── Core Identifiers ──────────────────────────────────────
    job_title: str = Field(
        ...,
        description="The primary job title extracted from the JD.",
        example="Senior AI Engineer"
    )

    extracted_raw_text: Optional[str] = Field(
        default=None,
        description="The raw text extracted from the uploaded file (if uploaded)."
    )

    # ── Experience Requirement ────────────────────────────────
    minimum_years_experience: int = Field(
        ...,
        ge=0,
        le=40,
        description=(
            "Minimum years of experience required as an integer. "
            "If a range is given (e.g. '5-9 years'), use the lower bound."
        ),
        example=5
    )
    maximum_years_experience: Optional[int] = Field(
        default=None,
        ge=0,
        le=40,
        description="Upper bound of experience range, if specified.",
        example=9
    )

    # ── Skills Classification ─────────────────────────────────
    must_have_skills: list[str] = Field(
        ...,
        description=(
            "Non-negotiable hard skills. Candidates without these "
            "should be ranked very low or filtered out."
        ),
        example=["Python", "embeddings", "vector databases", "evaluation frameworks"]
    )
    nice_to_have_skills: list[str] = Field(
        default=[],
        description=(
            "Preferred but not mandatory skills. Used to differentiate "
            "candidates who are already strong on must-haves."
        ),
        example=["LoRA", "QLoRA", "learning-to-rank", "distributed systems"]
    )

    # ── Behavioral & Soft Signals ─────────────────────────────
    behavioral_traits: list[str] = Field(
        default=[],
        description=(
            "Behavioral and cultural traits the JD signals. "
            "Maps to redrob_signals fields like recruiter_response_rate, "
            "interview_completion_rate, and open_to_work_flag."
        ),
        example=["bias for action", "strong written communication", "disagrees openly"]
    )

    # ── Domain & Industry Knowledge ───────────────────────────
    domain_knowledge: list[str] = Field(
        default=[],
        description=(
            "Domain-specific knowledge areas that are important for the role. "
            "Not just skills, but areas of expertise (e.g., 'HR-tech', "
            "'retrieval systems', 'A/B testing')."
        ),
        example=["information retrieval", "search systems", "HR-tech", "NLP"]
    )

    # ── Explicit Disqualifiers ────────────────────────────────
    disqualifiers: list[str] = Field(
        default=[],
        description=(
            "Explicit red flags mentioned in the JD that should penalize "
            "candidates in ranking. Extract these carefully — many JDs "
            "include them implicitly."
        ),
        example=[
            "pure research background with no production deployment",
            "only consulting firm experience (TCS, Infosys, Wipro, etc.)",
            "primary expertise in computer vision or speech without NLP"
        ]
    )

    # ── Location & Logistics ──────────────────────────────────
    preferred_locations: list[str] = Field(
        default=[],
        description="Preferred or required office locations.",
        example=["Pune", "Noida", "Delhi NCR", "Mumbai", "Hyderabad"]
    )
    remote_ok: bool = Field(
        default=False,
        description="Whether remote work is an acceptable arrangement."
    )
    preferred_notice_period_days: Optional[int] = Field(
        default=None,
        description=(
            "Maximum acceptable notice period in days. Candidates "
            "above this are penalised in availability scoring."
        ),
        example=30
    )

    # ── Seniority & Company Type Preferences ─────────────────
    preferred_company_types: list[str] = Field(
        default=[],
        description=(
            "Types of companies (product, startup, FAANG, consulting, etc.) "
            "that are preferred or penalised in the JD."
        ),
        example=["product companies", "startups"]
    )

    # ── Summary ───────────────────────────────────────────────
    key_responsibilities_summary: str = Field(
        ...,
        description=(
            "A concise 2-3 sentence summary of what the candidate "
            "will actually be doing day-to-day. No filler text."
        ),
        example=(
            "Own the intelligence layer (ranking, retrieval, matching) of a "
            "talent-intelligence platform. Ship an improved v2 ranking system "
            "using embeddings and hybrid retrieval within the first 8 weeks, "
            "and establish evaluation infrastructure for ongoing improvements."
        )
    )

    # ── Extraction Confidence ─────────────────────────────────
    extraction_confidence: str = Field(
        default="high",
        description="Model's self-assessed confidence in the extraction quality.",
        example="high"
    )

    @validator("extraction_confidence")
    def validate_confidence(cls, v):
        allowed = {"high", "medium", "low"}
        if v.lower() not in allowed:
            return "medium"
        return v.lower()

    @validator("job_title", pre=True, always=True)
    def validate_job_title(cls, v):
        if v is None or not str(v).strip():
            return "Unknown Position"
        return str(v).strip()

    @validator("minimum_years_experience", pre=True, always=True)
    def validate_min_exp(cls, v):
        if v is None:
            return 0
        try:
            return int(v)
        except (ValueError, TypeError):
            return 0

    @validator(
        "must_have_skills",
        "nice_to_have_skills",
        "behavioral_traits",
        "domain_knowledge",
        "disqualifiers",
        "preferred_locations",
        "preferred_company_types",
        pre=True,
        always=True
    )
    def validate_lists(cls, v):
        if v is None:
            return []
        if not isinstance(v, list):
            return [str(v)]
        return [str(item) for item in v if item is not None]

    @validator("key_responsibilities_summary", pre=True, always=True)
    def validate_summary(cls, v):
        if v is None or not str(v).strip():
            return "No key responsibilities summary provided."
        return str(v).strip()

    @validator("remote_ok", pre=True, always=True)
    def validate_remote_ok(cls, v):
        if v is None:
            return False
        if isinstance(v, bool):
            return v
        if str(v).lower() in {"true", "1", "yes", "y"}:
            return True
        return False

    class Config:
        json_schema_extra = {
            "example": {
                "job_title": "Senior AI Engineer",
                "minimum_years_experience": 5,
                "maximum_years_experience": 9,
                "must_have_skills": [
                    "Python", "embeddings-based retrieval", "vector databases",
                    "evaluation frameworks (NDCG/MRR)", "production ML deployment"
                ],
                "nice_to_have_skills": [
                    "LoRA/QLoRA fine-tuning", "learning-to-rank", "distributed systems",
                    "open-source contributions", "HR-tech experience"
                ],
                "behavioral_traits": [
                    "bias for shipping over researching",
                    "strong written communication",
                    "comfort with ambiguity"
                ],
                "domain_knowledge": [
                    "information retrieval", "hybrid search", "NLP", "LLM integration",
                    "A/B testing", "recommendation systems"
                ],
                "disqualifiers": [
                    "pure research without production deployment",
                    "only consulting firm background",
                    "computer vision/speech without NLP"
                ],
                "preferred_locations": ["Pune", "Noida", "Delhi NCR", "Mumbai", "Hyderabad"],
                "remote_ok": False,
                "preferred_notice_period_days": 30,
                "preferred_company_types": ["product companies", "startups"],
                "key_responsibilities_summary": (
                    "Own the full intelligence layer (ranking, retrieval, candidate-JD matching) "
                    "of an AI-native talent platform. Ship a demonstrably better v2 ranking "
                    "system within 8 weeks, then build the evaluation infrastructure and mentor "
                    "a growing team."
                ),
                "extraction_confidence": "high"
            }
        }
