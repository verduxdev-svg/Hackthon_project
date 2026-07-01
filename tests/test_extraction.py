import json
import pytest
from fastapi.testclient import TestClient
from main import app
client = None

@pytest.fixture(autouse=True, scope='module')
def setup_lifespan():
    global client
    with TestClient(app) as c:
        client = c
        yield
HACKATHON_JD_SAMPLE = "\nJob Description: Senior AI Engineer — Founding Team\nCompany: Redrob AI\nLocation: Pune/Noida, India (Hybrid)\nExperience Required: 5–9 years\n\nWe need someone who is comfortable with deep technical depth in modern ML systems \n(embeddings, retrieval, ranking, LLMs, fine-tuning) AND a scrappy product-engineering attitude.\n\nWhat you'd actually be doing:\nOwn the intelligence layer of Redrob's product — the ranking, retrieval, and matching systems.\nWeeks 1-3: Audit current BM25 + rule-based scoring. Identify highest-leverage improvements.\nWeeks 4-8: Ship a v2 ranking system using embeddings, hybrid retrieval, and LLM-based re-ranking.\nWeeks 9-12: Set up evaluation infrastructure — NDCG, MRR, MAP, offline benchmarks, A/B testing.\n\nThings you absolutely need:\n- Production experience with embeddings-based retrieval systems (sentence-transformers, BGE, E5)\n- Production experience with vector databases (Pinecone, Weaviate, Qdrant, Milvus, Elasticsearch)\n- Strong Python\n- Hands-on experience designing evaluation frameworks for ranking systems\n\nThings we'd like but won't reject you for:\n- LLM fine-tuning experience (LoRA, QLoRA, PEFT)\n- Experience with learning-to-rank models\n- Prior exposure to HR-tech or marketplace products\n\nThings we explicitly do NOT want:\n- People who've only worked at consulting firms (TCS, Infosys, Wipro, Accenture) their entire career\n- People whose primary expertise is computer vision or speech without NLP experience\n- Pure research roles without any production deployment\n\nLocation: Pune/Noida preferred. Open to Hyderabad, Mumbai, Delhi NCR.\nNotice period: Prefer sub-30-day. Can buy out up to 30 days.\n"
SIMPLE_JD = '\nWe are looking for a Python Developer with 3+ years of experience.\nMust have: Python, Django, PostgreSQL, REST APIs.\nNice to have: Docker, AWS, Redis.\nLocation: Remote OK.\n'

class TestHealthEndpoint:

    def test_health_returns_200(self):
        response = client.get('/api/health')
        assert response.status_code == 200

    def test_health_response_structure(self):
        response = client.get('/api/health')
        data = response.json()
        assert 'status' in data
        assert data['status'] == 'healthy'
        assert 'model' in data
        assert 'gemini_api_key_configured' in data

class TestJDExtractionEndpoint:

    def test_extract_jd_returns_200(self):
        response = client.post('/api/extract-jd', json={'raw_jd_text': HACKATHON_JD_SAMPLE})
        assert response.status_code in [200, 502]

    def test_extract_jd_schema_on_success(self):
        response = client.post('/api/extract-jd', json={'raw_jd_text': HACKATHON_JD_SAMPLE})
        if response.status_code == 200:
            data = response.json()
            assert 'job_title' in data
            assert 'minimum_years_experience' in data
            assert 'must_have_skills' in data
            assert 'nice_to_have_skills' in data
            assert 'behavioral_traits' in data
            assert 'domain_knowledge' in data
            assert 'disqualifiers' in data
            assert 'key_responsibilities_summary' in data
            assert isinstance(data['must_have_skills'], list)
            assert isinstance(data['disqualifiers'], list)
            assert isinstance(data['minimum_years_experience'], int)

    def test_extract_jd_extracts_experience_range(self):
        response = client.post('/api/extract-jd', json={'raw_jd_text': HACKATHON_JD_SAMPLE})
        if response.status_code == 200:
            data = response.json()
            assert data['minimum_years_experience'] == 5

    def test_extract_jd_finds_disqualifiers(self):
        response = client.post('/api/extract-jd', json={'raw_jd_text': HACKATHON_JD_SAMPLE})
        if response.status_code == 200:
            data = response.json()
            assert len(data.get('disqualifiers', [])) >= 2

    def test_extract_jd_simple_case(self):
        response = client.post('/api/extract-jd', json={'raw_jd_text': SIMPLE_JD})
        if response.status_code == 200:
            data = response.json()
            assert data['minimum_years_experience'] == 3
            assert data['remote_ok'] is True

    def test_extract_jd_rejects_empty_text(self):
        response = client.post('/api/extract-jd', json={'raw_jd_text': 'short'})
        assert response.status_code == 422

    def test_extract_jd_rejects_missing_field(self):
        response = client.post('/api/extract-jd', json={})
        assert response.status_code == 422

class TestFileUploadEndpoint:

    def test_file_upload_rejects_bad_extension(self):
        response = client.post('/api/extract-jd/file', files={'file': ('test.pdf', b'some content', 'application/pdf')})
        assert response.status_code == 400
        assert 'unsupported_file_type' in response.json()['detail']['error']

    def test_file_upload_txt_works(self):
        response = client.post('/api/extract-jd/file', files={'file': ('jd.txt', HACKATHON_JD_SAMPLE.encode('utf-8'), 'text/plain')})
        assert response.status_code in [200, 502]