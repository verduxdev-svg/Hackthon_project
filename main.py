import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
hf_offline = os.getenv('HF_HUB_OFFLINE', '0')
os.environ['HF_HUB_OFFLINE'] = hf_offline
os.environ['TRANSFORMERS_OFFLINE'] = os.getenv('TRANSFORMERS_OFFLINE', hf_offline)
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
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S', stream=sys.stdout)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info('=' * 60)
    logger.info('  AI Recruiter v2.0 — Starting Up')
    logger.info(f'  Model  : {settings.GEMINI_MODEL}')
    logger.info(f"  API Key: {('OK - Configured' if settings.GEMINI_API_KEY else 'MISSING — Set GEMINI_API_KEY in .env')}")
    logger.info('  Docs   : http://127.0.0.1:8000/docs')
    logger.info('=' * 60)
    app.state.extraction_service = JDExtractionService()
    logger.info('[OK] JDExtractionService initialized (Gemini + cache enabled)')
    app.state.ranking_service = CandidateRankingService()
    logger.info('[OK] CandidateRankingService initialized')
    app.state.candidate_loader = CandidateLoaderService()
    candidates = app.state.candidate_loader.load()
    logger.info(f'[OK] CandidateLoaderService initialized | {len(candidates)} candidates pre-loaded')
    logger.info('=' * 60)
    logger.info('  All systems ready. Happy recruiting! :)')
    logger.info('=' * 60)
    yield
    logger.info('AI Recruiter service shutting down. Goodbye.')
settings = get_settings()
app = FastAPI(title=settings.APP_TITLE, description=settings.APP_DESCRIPTION, version=settings.APP_VERSION, lifespan=lifespan, docs_url='/docs', redoc_url='/redoc', openapi_tags=[{'name': 'JD Extraction', 'description': 'Phase 1: Transform raw Job Description text into clean, validated JSON containing all hiring signals ready for candidate ranking.'}, {'name': 'Candidate Ranking', 'description': 'Phase 2: Score and rank candidates against an extracted JD using a hybrid weighted scoring engine — skills, experience, behavioral signals, location, availability, and hard disqualifier filters.'}, {'name': 'Health', 'description': 'Service health, config status, and candidate dataset info.'}], openapi_url='/openapi.json', contact={'name': 'AI Recruiter — Hackathon Submission', 'url': 'http://127.0.0.1:8000/docs'})
app.add_middleware(CORSMiddleware, allow_origins=settings.ALLOWED_ORIGINS, allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
app.mount('/static', StaticFiles(directory='app/static'), name='static')
app.include_router(jd_router)
app.include_router(ranking_router)

@app.get('/', include_in_schema=False)
async def root():
    return FileResponse('app/static/index.html')
if __name__ == '__main__':
    import uvicorn
    uvicorn.run('main:app', host='0.0.0.0', port=8000, reload=True, log_level='info')