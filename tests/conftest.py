"""Pytest fixtures and configuration."""

import asyncio
import os
from typing import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from ai_devops_assistant.database.models import Base


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    # Use in-memory SQLite for tests
    db_url = "sqlite+aiosqlite:///:memory:"
    engine = create_async_engine(db_url, echo=False)
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        yield session
    
    # Cleanup
    await engine.dispose()


@pytest.fixture
def mock_settings():
    """Mock settings for tests."""
    return {
        "enable_rag": True,
        "enable_k8s": True,
        "enable_sql": True,
        "enable_metrics": True,
        "enable_logs": True,
        "enable_pipeline": True,
    }


# Markers
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: unit tests")
    config.addinivalue_line("markers", "integration: integration tests")
    config.addinivalue_line("markers", "slow: slow tests")
    config.addinivalue_line("markers", "external: tests that call external services")
