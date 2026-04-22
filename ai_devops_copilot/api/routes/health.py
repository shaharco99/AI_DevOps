"""Health check endpoint."""

import logging
from datetime import datetime

from fastapi import APIRouter

from ai_devops_copilot.api.schemas import HealthResponse
from ai_devops_copilot.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint.
    
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
    
    Returns:
        dict: Status
    """
    return {"status": "alive"}


@router.get("/ready")
async def readiness_check() -> dict:
    """Kubernetes readiness probe endpoint.
    
    Returns:
        dict: Status
    """
    return {"status": "ready"}
