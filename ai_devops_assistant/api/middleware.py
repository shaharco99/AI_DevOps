"""API middleware for logging, error handling, and monitoring."""

import logging
import time
from datetime import datetime
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for request/response logging."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log request and response."""
        start_time = time.time()
        
        # Log request
        logger.debug(
            f"Request: {request.method} {request.url.path} "
            f"Client: {request.client.host if request.client else 'Unknown'}"
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
            f"Response: {request.method} {request.url.path} "
            f"Status: {response.status_code} Duration: {duration_ms:.2f}ms"
        )

        # Add response headers
        response.headers["X-Process-Time"] = str(duration_ms)
        
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
