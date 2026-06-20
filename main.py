"""
FastAPI Application Entry Point — Phase 1: JD Intelligence Extractor

This is the main application file. It:
- Creates the FastAPI app with full metadata for Swagger UI
- Configures CORS middleware (for React frontend)
- Registers all routers
- Sets up structured logging
- Provides startup/shutdown lifecycle hooks
"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.core.config import get_settings
from app.routers.jd_router import router as jd_router

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
# App Lifespan (startup / shutdown hooks)
# ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs startup logic before serving, cleanup on shutdown."""
    settings = get_settings()
    logger.info("=" * 60)
    logger.info("  Phase 1: JD Intelligence Extractor — Starting Up")
    logger.info(f"  Model  : {settings.GROQ_MODEL}")
    logger.info(f"  API Key: {'✓ Configured' if settings.GROQ_API_KEY else '✗ MISSING — Set GROQ_API_KEY in .env'}")
    logger.info("  Docs   : http://127.0.0.1:8000/docs")
    logger.info("=" * 60)
    yield
    logger.info("Phase 1 service shutting down. Goodbye.")


# ─────────────────────────────────────────────────────────────
# FastAPI App Instantiation
# ─────────────────────────────────────────────────────────────
settings = get_settings()

app = FastAPI(
    title=settings.APP_TITLE,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    lifespan=lifespan,

    # ── Swagger UI customization ──────────────────────────────
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {
            "name": "JD Extraction",
            "description": (
                "Core Phase 1 endpoints. Transform raw Job Description text into "
                "clean, validated JSON ready for the ranking pipeline."
            ),
        },
        {
            "name": "Health",
            "description": "Service health and configuration status.",
        },
    ],
    openapi_url="/openapi.json",
    contact={
        "name": "Phase 1 — AI Recruiter Hackathon",
        "url": "http://127.0.0.1:8000/docs",
    },
)

# ─────────────────────────────────────────────────────────────
# CORS Middleware (required for React frontend)
# ─────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────
# Register Routers
# ─────────────────────────────────────────────────────────────
app.include_router(jd_router)


# ─────────────────────────────────────────────────────────────
# Root Redirect → Swagger UI
# ─────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def root():
    """Redirect root URL to the Swagger UI for easy access."""
    return RedirectResponse(url="/docs")


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
