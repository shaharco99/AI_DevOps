"""Dependency injection for FastAPI routes."""

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from ai_devops_copilot.config.settings import settings
from ai_devops_copilot.database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session for routes."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_settings() -> dict:
    """Get application settings as dependency."""
    return {
        "enable_rag": settings.ENABLE_RAG,
        "enable_k8s": settings.ENABLE_K8S_TOOL,
        "enable_sql": settings.ENABLE_SQL_TOOL,
        "enable_metrics": settings.ENABLE_METRICS_TOOL,
        "enable_logs": settings.ENABLE_LOG_TOOL,
        "enable_pipeline": settings.ENABLE_PIPELINE_TOOL,
    }
