import pytest
import time
from app.services.ranking_service import CandidateRankingService
from app.models.jd_models import JDExtractionResult
from app.models.ranking_models import Candidate, CandidateSkill, CandidateProfile

def test_ranking_scale():
    jd = JDExtractionResult(
        job_title="Python Developer",
        minimum_years_experience=3,
        maximum_years_experience=7,
        must_have_skills=["Python", "FastAPI"],
        nice_to_have_skills=["Docker", "AWS"],
        behavioral_traits=[],
        domain_knowledge=[],
        disqualifiers=["consulting-only experience"],
        preferred_locations=[],
        remote_ok=True,
        preferred_notice_period_days=30,
        preferred_company_types=[],
        key_responsibilities_summary="Write clean Python code.",
        extraction_confidence="high"
    )
    
    candidates = []
    for i in range(1000):
        skills = [CandidateSkill(name="Python", proficiency="expert", years=5.0)]
        if i % 2 == 0:
            skills.append(CandidateSkill(name="FastAPI", proficiency="intermediate", years=2.0))
        if i % 3 == 0:
            skills.append(CandidateSkill(name="Docker", proficiency="beginner", years=1.0))
            
        cand = Candidate(
            candidate_id=f"C-{i}",
            name=f"Candidate {i}",
            summary=f"Python developer with {i%5+1} years of experience.",
            profile=CandidateProfile(years_of_experience=float(i%5+1), location="Pune"),
            skills=skills,
            career_history=[]
        )
        candidates.append(cand)
        
    ranking_svc = CandidateRankingService()
    
    t0 = time.time()
    result = ranking_svc.rank(jd, candidates, shortlist_size=10)
    t1 = time.time()
    
    duration = t1 - t0
    assert len(result.shortlist) == 10
    assert result.total_candidates_evaluated == 1000
    assert duration < 5.0
