"""
FastAPI Application Entry Point — AI Recruiter v2.0
Full pipeline: JD Intelligence Extraction → Candidate Ranking

This file:
- Creates the FastAPI app with Swagger UI
- Initializes all services as TRUE SINGLETONS in app.state (lifespan)
- Registers all routers (JD extraction + candidate ranking)
- Configures CORS + structured logging
"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.routers.jd_router import router as jd_router
from app.routers.ranking_router import router as ranking_router
from app.services.extraction_service import JDExtractionService
from app.services.ranking_service import CandidateRankingService
from app.services.candidate_loader import CandidateLoaderService

# ─────────────────────────────────────────────────────────────
# Logging Configuration
# ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# App Lifespan — Initialize all services ONCE as singletons
# ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: Initialize all services once and store in app.state.
    Shutdown: Clean up resources.

    Using app.state for singletons ensures:
    - No per-request client creation overhead
    - JD extraction cache persists across requests
    - Candidate data loaded once from disk
    """
    settings = get_settings()
    logger.info("=" * 60)
    logger.info("  AI Recruiter v2.0 — Starting Up")
    logger.info(f"  Model  : {settings.GEMINI_MODEL}")
    logger.info(f"  API Key: {'OK - Configured' if settings.GEMINI_API_KEY else 'MISSING — Set GEMINI_API_KEY in .env'}")
    logger.info("  Docs   : http://127.0.0.1:8000/docs")
    logger.info("=" * 60)

    # ── Initialize services as singletons ────────────────────
    app.state.extraction_service = JDExtractionService()
    logger.info("[OK] JDExtractionService initialized (Gemini + cache enabled)")

    app.state.ranking_service = CandidateRankingService()
    logger.info("✓ CandidateRankingService initialized")

    app.state.candidate_loader = CandidateLoaderService()
    candidates = app.state.candidate_loader.load()
    logger.info(f"✓ CandidateLoaderService initialized | {len(candidates)} candidates pre-loaded")

    logger.info("=" * 60)
    logger.info("  All systems ready. Happy recruiting! 🚀")
    logger.info("=" * 60)

    yield

    logger.info("AI Recruiter service shutting down. Goodbye.")


# ─────────────────────────────────────────────────────────────
# FastAPI App Instantiation
# ─────────────────────────────────────────────────────────────
settings = get_settings()

app = FastAPI(
    title=settings.APP_TITLE,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {
            "name": "JD Extraction",
            "description": (
                "Phase 1: Transform raw Job Description text into clean, validated JSON "
                "containing all hiring signals ready for candidate ranking."
            ),
        },
        {
            "name": "Candidate Ranking",
            "description": (
                "Phase 2: Score and rank candidates against an extracted JD using a "
                "hybrid weighted scoring engine — skills, experience, behavioral signals, "
                "location, availability, and hard disqualifier filters."
            ),
        },
        {
            "name": "Health",
            "description": "Service health, config status, and candidate dataset info.",
        },
    ],
    openapi_url="/openapi.json",
    contact={
        "name": "AI Recruiter — Hackathon Submission",
        "url": "http://127.0.0.1:8000/docs",
    },
)

# ─────────────────────────────────────────────────────────────
# CORS Middleware
# ─────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────
# Mount Static Files (Frontend UI)
# ─────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ─────────────────────────────────────────────────────────────
# Register Routers
# ─────────────────────────────────────────────────────────────
app.include_router(jd_router)
app.include_router(ranking_router)


# ─────────────────────────────────────────────────────────────
# Root → Serve Frontend UI
# ─────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def root():
    """Serve the frontend UI at root."""
    return FileResponse("app/static/index.html")


# ─────────────────────────────────────────────────────────────
# Run directly (alternative to uvicorn CLI)
# ─────────────────────────────────────────────────────────────
# To start: uvicorn main:app --reload --port 8000
# Or:       python main.py
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
