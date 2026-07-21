"""Health check endpoints."""

import logging
from datetime import datetime

from fastapi import APIRouter
from sqlalchemy import text
from starlette.responses import JSONResponse

from ai_devops_assistant.api.schemas import HealthResponse
from ai_devops_assistant.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Shallow health check endpoint (process is up).

    Returns:
        HealthResponse: Health status information
    """
    return HealthResponse(
        status="healthy",
        version=settings.APP_VERSION,
        environment=settings.API_ENVIRONMENT,
        timestamp=datetime.utcnow(),
    )


@router.get("/live")
async def liveness_check() -> dict:
    """Kubernetes liveness probe endpoint.

    Deliberately shallow: liveness must not depend on downstreams,
    otherwise a DB outage would restart-loop every pod.

    Returns:
        dict: Status
    """
    return {"status": "alive"}


async def _check_database() -> tuple[bool, str]:
    """Ping the database with a trivial query."""
    from ai_devops_assistant.database.session import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as e:
        logger.error(f"Readiness DB check failed: {e}")
        return False, str(e)


async def _check_llm() -> tuple[bool, str]:
    """Check the configured LLM backend (Ollama or Anthropic)."""
    from ai_devops_assistant.services.llm_service import get_llm_service

    try:
        service = await get_llm_service()
        healthy = await service.health_check()
        return healthy, "ok" if healthy else "unreachable"
    except Exception as e:
        logger.error(f"Readiness LLM check failed: {e}")
        return False, str(e)


@router.get("/ready")
async def readiness_check() -> JSONResponse:
    """Kubernetes readiness probe endpoint.

    Verifies the dependencies the request path actually needs (database and
    LLM backend) and returns 503 with per-dependency detail when any fail.

    Returns:
        JSONResponse: Per-dependency status, 200 if all healthy else 503
    """
    db_ok, db_detail = await _check_database()
    llm_ok, llm_detail = await _check_llm()

    ready = db_ok and llm_ok
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ready" if ready else "not_ready",
            "checks": {
                "database": {"healthy": db_ok, "detail": db_detail},
                "llm": {"healthy": llm_ok, "detail": llm_detail},
            },
        },
    )
