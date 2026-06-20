# Phase 1: JD Intelligence Extractor 🧠

> **Hackathon Project — AI Recruiter | Redrob Intelligent Candidate Discovery Challenge**

A production-quality FastAPI microservice that transforms messy, unstructured Job Description text into clean, validated JSON — the foundation for Phase 2's candidate ranking engine.

---

## ⚡ 60-Second Quickstart

### 1. Get your FREE Groq API key
Go to **https://console.groq.com** → Create account → Copy your API key (starts with `gsk_`)

### 2. Configure the environment
```bash
# In the phase1-jd-extractor/ directory:
copy .env.example .env
# Then open .env and paste your Groq API key
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Start the server
```bash
uvicorn main:app --reload
```

### 5. Open Swagger UI
Go to → **http://127.0.0.1:8000/docs**

Click `POST /api/extract-jd` → **Try it out** → paste any job description → **Execute**

---

## 🏗️ Architecture

```
phase1-jd-extractor/
│
├── main.py                         # FastAPI app entry point
│
├── app/
│   ├── core/
│   │   └── config.py               # Pydantic Settings (env vars, model config)
│   │
│   ├── models/
│   │   └── jd_models.py            # Pydantic I/O schemas (JDRequest + JDExtractionResult)
│   │
│   ├── services/
│   │   └── extraction_service.py   # Core: Groq API + prompt engineering + validation
│   │
│   └── routers/
│       └── jd_router.py            # FastAPI route handlers (3 endpoints)
│
├── tests/
│   └── test_extraction.py          # Pytest test suite
│
├── requirements.txt
├── .env.example                    # Template — copy to .env and add your key
└── .gitignore
```

### Request → Response Flow

```
React Frontend / Postman
        │
        │  POST /api/extract-jd
        │  { "raw_jd_text": "We are hiring a Senior AI Engineer..." }
        ▼
┌─────────────────────────────────┐
│  FastAPI (jd_router.py)         │
│  • Input validation (Pydantic)  │
│  • Route to extraction service  │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│  JDExtractionService            │
│  • Assembles prompt             │
│  • Calls Groq API               │
│    (Llama 3.3 70B, JSON mode)   │
│  • Parses JSON response         │
│  • Validates with Pydantic      │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────┐
│  JDExtractionResult (validated JSON)                    │
│                                                         │
│  {                                                      │
│    "job_title": "Senior AI Engineer",                   │
│    "minimum_years_experience": 5,                       │
│    "maximum_years_experience": 9,                       │
│    "must_have_skills": [                                │
│      "Python", "embeddings-based retrieval",            │
│      "vector databases", "evaluation frameworks"        │
│    ],                                                   │
│    "nice_to_have_skills": ["LoRA", "learning-to-rank"], │
│    "behavioral_traits": ["bias for shipping"],          │
│    "domain_knowledge": ["information retrieval", "NLP"],│
│    "disqualifiers": [                                   │
│      "consulting-only background",                      │
│      "computer vision without NLP"                      │
│    ],                                                   │
│    "preferred_locations": ["Pune", "Noida"],            │
│    "remote_ok": false,                                  │
│    "preferred_notice_period_days": 30,                  │
│    "preferred_company_types": ["product companies"],    │
│    "key_responsibilities_summary": "...",               │
│    "extraction_confidence": "high"                      │
│  }                                                      │
└─────────────────────────────────────────────────────────┘
```

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/extract-jd` | **Core endpoint** — Extract from raw JD text |
| `POST` | `/api/extract-jd/file` | Upload a `.docx` or `.txt` JD file |
| `GET` | `/api/health` | Service health + config status |
| `GET` | `/docs` | Swagger UI (interactive API docs) |
| `GET` | `/redoc` | ReDoc UI (clean reference docs) |

---

## 📦 Output Schema — Why Each Field Matters

The schema is designed to directly feed Phase 2 (candidate ranking). Every field maps to a signal in the `sample_candidates.json` dataset:

| JD Field | Maps to Candidate Signal |
|----------|--------------------------|
| `must_have_skills` | `candidate.skills[].name` + `proficiency` |
| `minimum_years_experience` | `candidate.profile.years_of_experience` |
| `disqualifiers` | `candidate.profile.current_industry`, `career_history[].company` |
| `preferred_notice_period_days` | `candidate.redrob_signals.notice_period_days` |
| `behavioral_traits` | `candidate.redrob_signals.interview_completion_rate`, `recruiter_response_rate` |
| `preferred_locations` | `candidate.profile.location` + `willing_to_relocate` |
| `preferred_company_types` | `candidate.career_history[].company_size` + industry |

### The Disqualifiers Field — The Hackathon's Secret Weapon 🎯

Most JD parsers ignore disqualifiers. The hackathon JD has an entire section called **"Things we explicitly do NOT want"**. Extracting these lets Phase 2 actively **penalise** keyword-stuffers — which the judges explicitly said is the winning strategy:

> *"The right answer involves reasoning about the gap between what the JD says and what the JD means."*

---

## 🧪 Testing

```bash
# Run full test suite
python -m pytest tests/ -v

# Run health check (no API key needed)
curl http://127.0.0.1:8000/api/health

# Test with the actual hackathon JD file
# (requires API key in .env)
curl -X POST http://127.0.0.1:8000/api/extract-jd/file \
  -F "file=@../job_description.docx"
```

---

## 🔑 Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Framework | **FastAPI** | Async, auto-Swagger, industry standard for AI APIs |
| LLM Provider | **Groq Cloud** | Free tier, <1s latency, JSON mode enforced |
| Model | **Llama 3.3 70B** | Best reasoning for structured extraction |
| Validation | **Pydantic v2** | Runtime schema enforcement — no bad data enters Phase 2 |
| Config | **pydantic-settings** | Fail-fast if GROQ_API_KEY is missing |
| File Parsing | **python-docx** | Reads the `.docx` hackathon JD directly |

---

## 🚀 What Feeds Into Phase 2

The `JDExtractionResult` JSON is your **ranking specification**. Phase 2 will:

1. Load all 50 candidates from `sample_candidates.json`
2. Score each candidate against every field in this JSON
3. Apply hard filters (`disqualifiers`) first
4. Apply soft scoring on `must_have_skills`, `nice_to_have_skills`, `domain_knowledge`
5. Weight by `redrob_signals` (activity, response rate, availability)
6. Return a ranked list of the top candidates

> **Phase 1 output quality directly determines Phase 2 ranking quality.** A bad extraction means a wrong ranking.
