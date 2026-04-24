"""API middleware for logging, error handling, and monitoring."""

import logging
import time
from collections.abc import Callable
from datetime import datetime

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ai_devops_assistant.observability.ai_observability import (
    generate_request_id,
    set_request_id,
)

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for request/response logging."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log request and response."""
        start_time = time.time()
        request_id = request.headers.get("X-Request-ID", generate_request_id())
        set_request_id(request_id)

        # Log request
        logger.debug(
            "request_started",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "client": request.client.host if request.client else "unknown",
            },
        )

        try:
            response = await call_next(request)
        except Exception as e:
            logger.error(f"Request failed: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

        # Calculate request duration
        duration_ms = (time.time() - start_time) * 1000

        # Log response
        logger.debug(
            "request_finished",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )

        # Add response headers
        response.headers["X-Process-Time"] = str(duration_ms)
        response.headers["X-Request-ID"] = request_id

        return response


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware for global error handling."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Handle errors globally."""
        try:
            response = await call_next(request)
            return response
        except ValueError as e:
            logger.error(f"Validation error: {e}")
            return JSONResponse(
                status_code=400,
                content={
                    "error": str(e),
                    "code": "VALIDATION_ERROR",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
