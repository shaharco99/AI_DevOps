"""FastAPI application factory and configuration."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ai_devops_assistant.config.logging import setup_logging
from ai_devops_assistant.config.settings import settings

# Configure logging
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.API_ENVIRONMENT}")
    logger.info(f"LLM Model: {settings.LLM_MODEL}")
    logger.info(
        f"Database URL: {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'N/A'}"
    )

    try:
        # Initialize database
        from ai_devops_assistant.database.session import close_db, init_db

        await init_db()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")

    yield

    # Shutdown
    try:
        from ai_devops_assistant.database.session import close_db
        from ai_devops_assistant.services.llm_service import close_llm_service

        await close_db()
        await close_llm_service()
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

    logger.info(f"Shutting down {settings.APP_NAME}")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        description="An AI-powered DevOps assistant for analyzing logs, infrastructure, and providing intelligent recommendations.",
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )

    # Rate limiting (decorator-based limits on chat/run_sql endpoints)
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    from ai_devops_assistant.api.auth import limiter, require_api_key

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Include routes; expensive/mutating routes require X-API-Key when API_KEY is set
    from fastapi import Depends

    from ai_devops_assistant.api.routes import analyze_logs, auth, chat, health, metrics, run_sql

    auth_deps = [Depends(require_api_key)]
    app.include_router(health.router)
    # No auth dependency: this is where a caller trades an API key for a session.
    app.include_router(auth.router)
    app.include_router(chat.router, dependencies=auth_deps)
    app.include_router(run_sql.router, dependencies=auth_deps)
    app.include_router(analyze_logs.router, dependencies=auth_deps)
    app.include_router(metrics.router)

    # Add middleware
    from fastapi.middleware.cors import CORSMiddleware
    from starlette.middleware.trustedhost import TrustedHostMiddleware

    from ai_devops_assistant.api.middleware import ErrorHandlingMiddleware, LoggingMiddleware

    app.add_middleware(LoggingMiddleware)
    app.add_middleware(ErrorHandlingMiddleware)
    # "*" means no Host restriction — skip the middleware entirely. Outside
    # production, allow the test client's default host so local pytest runs pass.
    allowed_hosts = settings.ALLOWED_HOSTS
    if "*" not in allowed_hosts:
        if not settings.is_production:
            allowed_hosts = [*allowed_hosts, "testserver"]
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    if settings.CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    logger.debug("FastAPI application created successfully")
    return app


# Create the application instance
app = create_app()
