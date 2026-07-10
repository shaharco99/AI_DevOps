"""API-key authentication and rate limiting."""

import logging

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from slowapi import Limiter
from slowapi.util import get_remote_address

from ai_devops_assistant.config.settings import settings

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Shared limiter for @limiter.limit(...) decorators on endpoints
limiter = Limiter(key_func=get_remote_address, enabled=settings.RATE_LIMIT_ENABLED)


async def require_api_key(api_key: str = Security(api_key_header)) -> None:
    """Reject requests without a valid X-API-Key header.

    Auth is disabled when settings.API_KEY is unset (local demo mode).
    """
    if not settings.API_KEY:
        if settings.is_production:
            logger.warning("API_KEY is not set — API routes are unauthenticated in production")
        return

    if api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
