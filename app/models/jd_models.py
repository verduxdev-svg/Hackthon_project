from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional

class JDRequest(BaseModel):
    raw_jd_text: str = Field(..., min_length=50, description='The raw, unstructured job description text to be parsed.', json_schema_extra={'example': 'We are hiring a Senior Machine Learning Engineer with 5+ years of experience in Python, PyTorch, and production deployment of ML models...'})

class JDExtractionResult(BaseModel):
    job_title: str = Field(..., description='The primary job title extracted from the JD.', json_schema_extra={'example': 'Senior AI Engineer'})
    extracted_raw_text: Optional[str] = Field(default=None, description='The raw text extracted from the uploaded file (if uploaded).')
    minimum_years_experience: int = Field(..., ge=0, le=40, description="Minimum years of experience required as an integer. If a range is given (e.g. '5-9 years'), use the lower bound.", json_schema_extra={'example': 5})
    maximum_years_experience: Optional[int] = Field(default=None, ge=0, le=40, description='Upper bound of experience range, if specified.', json_schema_extra={'example': 9})
    must_have_skills: list[str] = Field(..., description='Non-negotiable hard skills. Candidates without these should be ranked very low or filtered out.', json_schema_extra={'example': ['Python', 'embeddings', 'vector databases', 'evaluation frameworks']})
    nice_to_have_skills: list[str] = Field(default=[], description='Preferred but not mandatory skills. Used to differentiate candidates who are already strong on must-haves.', json_schema_extra={'example': ['LoRA', 'QLoRA', 'learning-to-rank', 'distributed systems']})
    behavioral_traits: list[str] = Field(default=[], description='Behavioral and cultural traits the JD signals. Maps to redrob_signals fields like recruiter_response_rate, interview_completion_rate, and open_to_work_flag.', json_schema_extra={'example': ['bias for action', 'strong written communication', 'disagrees openly']})
    domain_knowledge: list[str] = Field(default=[], description="Domain-specific knowledge areas that are important for the role. Not just skills, but areas of expertise (e.g., 'HR-tech', 'retrieval systems', 'A/B testing').", json_schema_extra={'example': ['information retrieval', 'search systems', 'HR-tech', 'NLP']})
    disqualifiers: list[str] = Field(default=[], description='Explicit red flags mentioned in the JD that should penalize candidates in ranking. Extract these carefully — many JDs include them implicitly.', json_schema_extra={'example': ['pure research background with no production deployment', 'only consulting firm experience (TCS, Infosys, Wipro, etc.)', 'primary expertise in computer vision or speech without NLP']})
    preferred_locations: list[str] = Field(default=[], description='Preferred or required office locations.', json_schema_extra={'example': ['Pune', 'Noida', 'Delhi NCR', 'Mumbai', 'Hyderabad']})
    remote_ok: bool = Field(default=False, description='Whether remote work is an acceptable arrangement.')
    preferred_notice_period_days: Optional[int] = Field(default=None, description='Maximum acceptable notice period in days. Candidates above this are penalised in availability scoring.', json_schema_extra={'example': 30})
    preferred_company_types: list[str] = Field(default=[], description='Types of companies (product, startup, FAANG, consulting, etc.) that are preferred or penalised in the JD.', json_schema_extra={'example': ['product companies', 'startups']})
    key_responsibilities_summary: str = Field(..., description='A concise 2-3 sentence summary of what the candidate will actually be doing day-to-day. No filler text.', json_schema_extra={'example': 'Own the intelligence layer (ranking, retrieval, matching) of a talent-intelligence platform. Ship an improved v2 ranking system using embeddings and hybrid retrieval within the first 8 weeks, and establish evaluation infrastructure for ongoing improvements.'})
    extraction_confidence: str = Field(default='high', description="Model's self-assessed confidence in the extraction quality.", json_schema_extra={'example': 'high'})

    @field_validator('extraction_confidence')
    @classmethod
    def validate_confidence(cls, v):
        allowed = {'high', 'medium', 'low'}
        if v.lower() not in allowed:
            return 'medium'
        return v.lower()

    @field_validator('job_title', mode='before')
    @classmethod
    def validate_job_title(cls, v):
        if v is None or not str(v).strip():
            return 'Unknown Position'
        return str(v).strip()

    @field_validator('minimum_years_experience', mode='before')
    @classmethod
    def validate_min_exp(cls, v):
        if v is None:
            return 0
        try:
            return int(v)
        except (ValueError, TypeError):
            return 0

    @field_validator('must_have_skills', 'nice_to_have_skills', 'behavioral_traits', 'domain_knowledge', 'disqualifiers', 'preferred_locations', 'preferred_company_types', mode='before')
    @classmethod
    def validate_lists(cls, v):
        if v is None:
            return []
        if not isinstance(v, list):
            return [str(v)]
        return [str(item) for item in v if item is not None]

    @field_validator('key_responsibilities_summary', mode='before')
    @classmethod
    def validate_summary(cls, v):
        if v is None or not str(v).strip():
            return 'No key responsibilities summary provided.'
        return str(v).strip()

    @field_validator('remote_ok', mode='before')
    @classmethod
    def validate_remote_ok(cls, v):
        if v is None:
            return False
        if isinstance(v, bool):
            return v
        if str(v).lower() in {'true', '1', 'yes', 'y'}:
            return True
        return False

    model_config = ConfigDict(
        json_schema_extra={'example': {'job_title': 'Senior AI Engineer', 'minimum_years_experience': 5, 'maximum_years_experience': 9, 'must_have_skills': ['Python', 'embeddings-based retrieval', 'vector databases', 'evaluation frameworks (NDCG/MRR)', 'production ML deployment'], 'nice_to_have_skills': ['LoRA/QLoRA fine-tuning', 'learning-to-rank', 'distributed systems', 'open-source contributions', 'HR-tech experience'], 'behavioral_traits': ['bias for shipping over researching', 'strong written communication', 'comfort with ambiguity'], 'domain_knowledge': ['information retrieval', 'hybrid search', 'NLP', 'LLM integration', 'A/B testing', 'recommendation systems'], 'disqualifiers': ['pure research without production deployment', 'only consulting firm background', 'computer vision/speech without NLP'], 'preferred_locations': ['Pune', 'Noida', 'Delhi NCR', 'Mumbai', 'Hyderabad'], 'remote_ok': False, 'preferred_notice_period_days': 30, 'preferred_company_types': ['product companies', 'startups'], 'key_responsibilities_summary': 'Own the full intelligence layer (ranking, retrieval, candidate-JD matching) of an AI-native talent platform. Ship a demonstrably better v2 ranking system within 8 weeks, then build the evaluation infrastructure and mentor a growing team.', 'extraction_confidence': 'high'}}
    )