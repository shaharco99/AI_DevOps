"""FastAPI application factory and configuration."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_devops_copilot.config.logging import setup_logging
from ai_devops_copilot.config.settings import settings

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
    logger.info(f"Database URL: {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'N/A'}")
    
    try:
        # Initialize database
        from ai_devops_copilot.database.session import init_db, close_db
        await init_db()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
    
    yield
    
    # Shutdown
    try:
        from ai_devops_copilot.database.session import close_db
        from ai_devops_copilot.services.llm_service import close_ollama_service
        
        await close_db()
        await close_ollama_service()
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

    # Include routes
    from ai_devops_copilot.api.routes import health, chat

    app.include_router(health.router)
    app.include_router(chat.router)

    # Add middleware
    from ai_devops_copilot.api.middleware import LoggingMiddleware, ErrorHandlingMiddleware
    
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(ErrorHandlingMiddleware)

    logger.debug("FastAPI application created successfully")
    return app


# Create the application instance
app = create_app()
