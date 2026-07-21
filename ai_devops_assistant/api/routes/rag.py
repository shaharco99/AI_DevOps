"""Document ingestion into the RAG knowledge base."""

import logging

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from ai_devops_assistant.api.auth import limiter
from ai_devops_assistant.rag.loaders import (
    DocumentTooLargeError,
    UnsupportedDocumentError,
    extract_text_async,
    supported_extensions,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["rag"])


@router.get("/supported-types")
async def supported_types() -> dict:
    """File types the upload dialog should accept."""
    return {"extensions": supported_extensions()}


@router.post("/ingest")
@limiter.limit("10/minute")
async def ingest_document(request: Request, file: UploadFile = File(...)) -> dict:
    """Ingest an uploaded document into the knowledge base.

    Rate limited: parsing is comparatively expensive, and this is the one
    endpoint that hands user-supplied bytes to a document parser.

    Anything ingested here later reaches the model as retrieved context, so it
    is treated as untrusted from this point on — see agents/fencing.py.

    Args:
        request: Raw HTTP request (required by the rate limiter)
        file: The uploaded document

    Returns:
        dict: number of chunks ingested
    """
    filename = file.filename or "upload"
    data = await file.read()

    try:
        text = await extract_text_async(filename, data)
    except DocumentTooLargeError as e:
        raise HTTPException(status_code=413, detail=str(e)) from e
    except UnsupportedDocumentError as e:
        raise HTTPException(status_code=415, detail=str(e)) from e

    if not text.strip():
        raise HTTPException(status_code=422, detail=f"No text could be extracted from {filename}")

    try:
        from ai_devops_assistant.rag.pipeline import RAGPipeline

        pipeline = RAGPipeline()
        await pipeline.initialize()
        chunks = await pipeline.ingest_text(text, {"source": filename, "source_type": "upload"})
    except Exception as e:
        logger.error(f"Failed to ingest {filename}: {e}")
        raise HTTPException(status_code=503, detail="Knowledge base is unavailable") from e

    logger.info(f"Ingested {filename} as {chunks} chunks")
    return {"filename": filename, "chunks": chunks, "characters": len(text)}
