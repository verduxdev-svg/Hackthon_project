"""
Phase 1 Test Suite — JD Extraction Microservice

Tests the full extraction pipeline using the actual hackathon JD
(job_description.docx) and validates the output schema is correct.

Run:  python -m pytest tests/ -v
"""

import json
import pytest
from fastapi.testclient import TestClient

from main import app

client = None

@pytest.fixture(autouse=True, scope="module")
def setup_lifespan():
    global client
    with TestClient(app) as c:
        client = c
        yield

# ─────────────────────────────────────────────────────────────
# Sample JDs for testing
# ─────────────────────────────────────────────────────────────

# A condensed version of the hackathon JD
HACKATHON_JD_SAMPLE = """
Job Description: Senior AI Engineer — Founding Team
Company: Redrob AI
Location: Pune/Noida, India (Hybrid)
Experience Required: 5–9 years

We need someone who is comfortable with deep technical depth in modern ML systems 
(embeddings, retrieval, ranking, LLMs, fine-tuning) AND a scrappy product-engineering attitude.

What you'd actually be doing:
Own the intelligence layer of Redrob's product — the ranking, retrieval, and matching systems.
Weeks 1-3: Audit current BM25 + rule-based scoring. Identify highest-leverage improvements.
Weeks 4-8: Ship a v2 ranking system using embeddings, hybrid retrieval, and LLM-based re-ranking.
Weeks 9-12: Set up evaluation infrastructure — NDCG, MRR, MAP, offline benchmarks, A/B testing.

Things you absolutely need:
- Production experience with embeddings-based retrieval systems (sentence-transformers, BGE, E5)
- Production experience with vector databases (Pinecone, Weaviate, Qdrant, Milvus, Elasticsearch)
- Strong Python
- Hands-on experience designing evaluation frameworks for ranking systems

Things we'd like but won't reject you for:
- LLM fine-tuning experience (LoRA, QLoRA, PEFT)
- Experience with learning-to-rank models
- Prior exposure to HR-tech or marketplace products

Things we explicitly do NOT want:
- People who've only worked at consulting firms (TCS, Infosys, Wipro, Accenture) their entire career
- People whose primary expertise is computer vision or speech without NLP experience
- Pure research roles without any production deployment

Location: Pune/Noida preferred. Open to Hyderabad, Mumbai, Delhi NCR.
Notice period: Prefer sub-30-day. Can buy out up to 30 days.
"""

SIMPLE_JD = """
We are looking for a Python Developer with 3+ years of experience.
Must have: Python, Django, PostgreSQL, REST APIs.
Nice to have: Docker, AWS, Redis.
Location: Remote OK.
"""


# ─────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_health_returns_200(self):
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_health_response_structure(self):
        response = client.get("/api/health")
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"
        assert "model" in data
        assert "gemini_api_key_configured" in data


class TestJDExtractionEndpoint:
    def test_extract_jd_returns_200(self):
        """Full integration test — requires a real GEMINI_API_KEY in .env"""
        response = client.post(
            "/api/extract-jd",
            json={"raw_jd_text": HACKATHON_JD_SAMPLE}
        )
        # If no API key configured, this will 502 — expected in CI
        assert response.status_code in [200, 502]

    def test_extract_jd_schema_on_success(self):
        """Validates response structure when API key is present."""
        response = client.post(
            "/api/extract-jd",
            json={"raw_jd_text": HACKATHON_JD_SAMPLE}
        )
        if response.status_code == 200:
            data = response.json()
            assert "job_title" in data
            assert "minimum_years_experience" in data
            assert "must_have_skills" in data
            assert "nice_to_have_skills" in data
            assert "behavioral_traits" in data
            assert "domain_knowledge" in data
            assert "disqualifiers" in data
            assert "key_responsibilities_summary" in data
            assert isinstance(data["must_have_skills"], list)
            assert isinstance(data["disqualifiers"], list)
            assert isinstance(data["minimum_years_experience"], int)

    def test_extract_jd_extracts_experience_range(self):
        """Verifies that 5-9 years is parsed as min=5."""
        response = client.post(
            "/api/extract-jd",
            json={"raw_jd_text": HACKATHON_JD_SAMPLE}
        )
        if response.status_code == 200:
            data = response.json()
            assert data["minimum_years_experience"] == 5

    def test_extract_jd_finds_disqualifiers(self):
        """The hackathon JD has explicit disqualifiers — we must extract them."""
        response = client.post(
            "/api/extract-jd",
            json={"raw_jd_text": HACKATHON_JD_SAMPLE}
        )
        if response.status_code == 200:
            data = response.json()
            # Should have extracted at least 2 disqualifiers from the JD
            assert len(data.get("disqualifiers", [])) >= 2

    def test_extract_jd_simple_case(self):
        """Tests basic extraction on a simple JD."""
        response = client.post(
            "/api/extract-jd",
            json={"raw_jd_text": SIMPLE_JD}
        )
        if response.status_code == 200:
            data = response.json()
            assert data["minimum_years_experience"] == 3
            assert data["remote_ok"] is True

    def test_extract_jd_rejects_empty_text(self):
        """Input validation: too-short text must be rejected."""
        response = client.post(
            "/api/extract-jd",
            json={"raw_jd_text": "short"}
        )
        assert response.status_code == 422

    def test_extract_jd_rejects_missing_field(self):
        """Input validation: missing raw_jd_text must be rejected."""
        response = client.post("/api/extract-jd", json={})
        assert response.status_code == 422


class TestFileUploadEndpoint:
    def test_file_upload_rejects_bad_extension(self):
        """Only .docx and .txt are supported."""
        response = client.post(
            "/api/extract-jd/file",
            files={"file": ("test.pdf", b"some content", "application/pdf")}
        )
        assert response.status_code == 400
        assert "unsupported_file_type" in response.json()["detail"]["error"]

    def test_file_upload_txt_works(self):
        """Plain text files should be processed correctly."""
        response = client.post(
            "/api/extract-jd/file",
            files={"file": ("jd.txt", HACKATHON_JD_SAMPLE.encode("utf-8"), "text/plain")}
        )
        # 200 (with API key) or 502 (no key) — both are valid test outcomes
        assert response.status_code in [200, 502]
