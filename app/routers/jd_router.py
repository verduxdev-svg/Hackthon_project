import logging
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends, Request, status
from fastapi.responses import JSONResponse
from app.models.jd_models import JDRequest, JDExtractionResult
from app.services.extraction_service import JDExtractionService
from app.core.config import get_settings, Settings
logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api', tags=['JD Extraction'])

def get_extraction_service(request: Request) -> JDExtractionService:
    return request.app.state.extraction_service

@router.post('/extract-jd', response_model=JDExtractionResult, status_code=status.HTTP_200_OK, summary='Extract structured data from raw JD text', description='Accepts raw, unstructured Job Description text and returns a validated JSON object containing all hiring signals: skills (must-have vs nice-to-have), experience requirements, behavioral traits, disqualifiers, and logistical details. This is the primary endpoint for Phase 1 of the AI Recruiter pipeline.', response_description='Validated JD extraction result ready for Phase 2 ranking.')
async def extract_job_description(request: JDRequest, service: JDExtractionService=Depends(get_extraction_service)):
    logger.info(f'POST /api/extract-jd | text_length={len(request.raw_jd_text)}')
    try:
        result = await service.extract(request.raw_jd_text)
        return result
    except ValueError as e:
        logger.warning(f'Validation error during extraction: {e}')
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={'error': 'extraction_validation_failed', 'message': str(e), 'hint': "The LLM returned a response that couldn't be validated. Try again."})
    except RuntimeError as e:
        logger.error(f'Upstream Gemini API error: {e}')
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail={'error': 'upstream_api_failure', 'message': str(e), 'hint': 'Check your GEMINI_API_KEY and Gemini service status.'})
    except Exception as e:
        logger.exception(f'Unexpected error in extract_job_description: {e}')
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={'error': 'internal_server_error', 'message': 'An unexpected error occurred. Check server logs.'})

@router.post('/extract-jd/file', response_model=JDExtractionResult, status_code=status.HTTP_200_OK, summary='Extract structured data from an uploaded JD file', description='Upload a .docx or .txt Job Description file and receive a validated structured JSON extraction. Useful for directly testing with the provided job_description.docx from the hackathon dataset.')
async def extract_from_file(file: UploadFile=File(..., description='Upload a .docx or .txt job description file.'), service: JDExtractionService=Depends(get_extraction_service)):
    logger.info(f'POST /api/extract-jd/file | filename={file.filename} | content_type={file.content_type}')
    raw_text = ''
    try:
        content = await file.read()
        if file.filename.endswith('.txt'):
            raw_text = content.decode('utf-8', errors='ignore')
        elif file.filename.endswith('.docx'):
            try:
                import docx
                import io
                doc = docx.Document(io.BytesIO(content))
                raw_text = '\n'.join([para.text for para in doc.paragraphs if para.text.strip()])
            except ImportError:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={'error': 'missing_dependency', 'message': 'python-docx is required for .docx uploads. Run: pip install python-docx'})
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={'error': 'unsupported_file_type', 'message': f"File type '{file.filename}' is not supported. Use .docx or .txt"})
        if len(raw_text.strip()) < 50:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={'error': 'file_too_short', 'message': 'The extracted text from the file is too short to be a valid JD.'})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'File reading failed: {e}')
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={'error': 'file_read_error', 'message': str(e)})
    try:
        result = await service.extract(raw_text)
        result.extracted_raw_text = raw_text
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

@router.post('/clear-jd-cache', status_code=status.HTTP_200_OK, summary='Clear the parsed JD cache', tags=['JD Extraction'])
async def clear_jd_cache(request: Request, service: JDExtractionService=Depends(get_extraction_service)):
    service.clear_cache()
    return JSONResponse(content={'status': 'success', 'message': 'JD extraction cache cleared successfully.'})

@router.get('/health', status_code=status.HTTP_200_OK, summary='Service health check', tags=['Health'])
async def health_check(settings: Settings=Depends(get_settings)):
    api_key_configured = bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != 'YOUR_GEMINI_API_KEY_HERE')
    return JSONResponse(content={'status': 'healthy', 'phase': 'Phase 2 — AI Candidate Ranking', 'model': settings.GEMINI_MODEL, 'gemini_api_key_configured': api_key_configured, 'endpoints': {'extract_text': 'POST /api/extract-jd', 'extract_file': 'POST /api/extract-jd/file', 'rank_candidates': 'POST /api/rank-from-preloaded', 'docs': 'GET /docs', 'clear_cache': 'POST /api/clear-jd-cache'}})