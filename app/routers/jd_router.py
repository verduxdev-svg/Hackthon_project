"""
API Router for JD Extraction endpoints.

This file defines:
- POST /api/extract-jd       → Full extraction from raw text
- POST /api/extract-jd/file  → Extraction from uploaded .docx/.txt file
- GET  /api/health            → Health check for the service
"""

import logging
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends, Request, status
from fastapi.responses import JSONResponse

from app.models.jd_models import JDRequest, JDExtractionResult
from app.services.extraction_service import JDExtractionService
from app.core.config import get_settings, Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["JD Extraction"])

# ─────────────────────────────────────────────────────────────
# Dependency: Service Singleton (pulled from app.state)
# ─────────────────────────────────────────────────────────────

def get_extraction_service(request: Request) -> JDExtractionService:
    """
    Pulls the singleton JDExtractionService from app.state.
    The service is initialized ONCE at startup in main.py lifespan.
    This avoids creating a new Groq client on every request (major perf fix).
    """
    return request.app.state.extraction_service


# ─────────────────────────────────────────────────────────────
# ENDPOINT 1: Extract from Raw Text
# ─────────────────────────────────────────────────────────────

@router.post(
    "/extract-jd",
    response_model=JDExtractionResult,
    status_code=status.HTTP_200_OK,
    summary="Extract structured data from raw JD text",
    description=(
        "Accepts raw, unstructured Job Description text and returns a validated "
        "JSON object containing all hiring signals: skills (must-have vs nice-to-have), "
        "experience requirements, behavioral traits, disqualifiers, and logistical details. "
        "This is the primary endpoint for Phase 1 of the AI Recruiter pipeline."
    ),
    response_description="Validated JD extraction result ready for Phase 2 ranking."
)
async def extract_job_description(
    request: JDRequest,
    service: JDExtractionService = Depends(get_extraction_service),
):
    """
    **Phase 1 Core Endpoint**: Transforms messy JD text → clean structured JSON.

    **How it works:**
    1. Validates the input text is non-empty (≥50 chars)
    2. Assembles a surgical extraction prompt
    3. Calls Groq Cloud API (Llama 3.3 70B) with JSON mode enforced
    4. Validates the response against the JDExtractionResult Pydantic schema
    5. Returns the clean, validated JSON

    **Try it with:** Paste any job description into `raw_jd_text` and click Execute.
    """
    logger.info(f"POST /api/extract-jd | text_length={len(request.raw_jd_text)}")

    try:
        result = await service.extract(request.raw_jd_text)
        return result

    except ValueError as e:
        # Schema validation or JSON parse errors → 422
        logger.warning(f"Validation error during extraction: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "extraction_validation_failed",
                "message": str(e),
                "hint": "The LLM returned a response that couldn't be validated. Try again."
            }
        )

    except RuntimeError as e:
        # Groq API errors → 502 Bad Gateway
        logger.error(f"Upstream Groq API error: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "upstream_api_failure",
                "message": str(e),
                "hint": "Check your GROQ_API_KEY and Groq service status."
            }
        )

    except Exception as e:
        # Catch-all → 500
        logger.exception(f"Unexpected error in extract_job_description: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_server_error",
                "message": "An unexpected error occurred. Check server logs.",
            }
        )


# ─────────────────────────────────────────────────────────────
# ENDPOINT 2: Extract from Uploaded File (.docx or .txt)
# ─────────────────────────────────────────────────────────────

@router.post(
    "/extract-jd/file",
    response_model=JDExtractionResult,
    status_code=status.HTTP_200_OK,
    summary="Extract structured data from an uploaded JD file",
    description=(
        "Upload a .docx or .txt Job Description file and receive a validated "
        "structured JSON extraction. Useful for directly testing with the "
        "provided job_description.docx from the hackathon dataset."
    )
)
async def extract_from_file(
    file: UploadFile = File(
        ...,
        description="Upload a .docx or .txt job description file."
    ),
    service: JDExtractionService = Depends(get_extraction_service),
):
    """
    **File Upload Endpoint**: Upload a .docx or .txt file directly.

    Especially useful for testing with the hackathon's `job_description.docx`.
    Supports both .docx (Word) and .txt files.
    """
    logger.info(f"POST /api/extract-jd/file | filename={file.filename} | content_type={file.content_type}")

    raw_text = ""

    try:
        content = await file.read()

        if file.filename.endswith(".txt"):
            raw_text = content.decode("utf-8", errors="ignore")

        elif file.filename.endswith(".docx"):
            # Dynamically import python-docx only when needed
            try:
                import docx
                import io
                doc = docx.Document(io.BytesIO(content))
                raw_text = "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
            except ImportError:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "error": "missing_dependency",
                        "message": "python-docx is required for .docx uploads. Run: pip install python-docx",
                    }
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "unsupported_file_type",
                    "message": f"File type '{file.filename}' is not supported. Use .docx or .txt",
                }
            )

        if len(raw_text.strip()) < 50:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "file_too_short",
                    "message": "The extracted text from the file is too short to be a valid JD.",
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File reading failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "file_read_error", "message": str(e)}
        )

    # Reuse the same extraction logic
    try:
        result = await service.extract(raw_text)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


# ─────────────────────────────────────────────────────────────
# ENDPOINT 3: Health Check
# ─────────────────────────────────────────────────────────────

@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Service health check",
    tags=["Health"]
)
async def health_check(settings: Settings = Depends(get_settings)):
    """
    Returns the current service health status.
    Also confirms the API key is configured (without exposing it).
    """
    api_key_configured = bool(
        settings.GROQ_API_KEY and
        settings.GROQ_API_KEY != "gsk_your_free_groq_api_key_here"
    )

    return JSONResponse(
        content={
            "status": "healthy",
            "phase": "Phase 1 — JD Intelligence Extractor",
            "model": settings.GROQ_MODEL,
            "groq_api_key_configured": api_key_configured,
            "endpoints": {
                "extract_text": "POST /api/extract-jd",
                "extract_file": "POST /api/extract-jd/file",
                "docs": "GET /docs",
            }
        }
    )
