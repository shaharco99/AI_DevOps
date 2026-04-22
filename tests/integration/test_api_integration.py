"""Integration tests for the application."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from ai_devops_assistant.main import create_app
from ai_devops_assistant.database.models import ChatSession, ChatMessage


@pytest.fixture
def client(test_db_session: AsyncSession):
    """Test client with database session."""
    app = create_app()
    # Override database dependency for testing
    from ai_devops_assistant.database.session import get_db_session

    async def override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db_session] = override_get_db
    return TestClient(app)


@pytest.mark.asyncio
async def test_full_chat_flow(client, test_db_session: AsyncSession):
    """Test complete chat flow with database persistence."""
    # Send a chat message
    response = client.post("/chat", json={"message": "Hello, check system status"})
    assert response.status_code == 200

    data = response.json()
    assert "response" in data
    assert "session_id" in data

    session_id = data["session_id"]

    # Verify session was created in database
    result = await test_db_session.execute(
        "SELECT id FROM chat_sessions WHERE id = :session_id",
        {"session_id": session_id}
    )
    session = result.fetchone()
    assert session is not None

    # Verify message was stored
    result = await test_db_session.execute(
        "SELECT content FROM chat_messages WHERE session_id = :session_id",
        {"session_id": session_id}
    )
    messages = result.fetchall()
    assert len(messages) >= 1  # At least the user message


@pytest.mark.asyncio
async def test_sql_query_integration(client, test_db_session: AsyncSession):
    """Test SQL query execution through API."""
    # First create some test data
    await test_db_session.execute(
        "INSERT INTO application_logs (timestamp, level, message, source) VALUES "
        "(datetime('now'), 'INFO', 'Test log message', 'test')"
    )
    await test_db_session.commit()

    # Query the data
    response = client.post("/run_sql", json={"query": "SELECT COUNT(*) FROM application_logs"})
    assert response.status_code == 200

    data = response.json()
    assert "results" in data
    assert len(data["results"]) > 0


@pytest.mark.asyncio
async def test_log_analysis_integration(client, test_db_session: AsyncSession):
    """Test log analysis through API."""
    # Create test log data
    await test_db_session.execute(
        "INSERT INTO application_logs (timestamp, level, message, source) VALUES "
        "(datetime('now'), 'ERROR', 'Database connection failed', 'api'), "
        "(datetime('now'), 'INFO', 'Application started successfully', 'main')"
    )
    await test_db_session.commit()

    # Analyze logs
    response = client.post("/analyze_logs", json={"query": "error logs"})
    assert response.status_code == 200

    data = response.json()
    assert "analysis" in data
    assert "Database connection failed" in data["analysis"]


@pytest.mark.asyncio
async def test_metrics_integration(client, test_db_session: AsyncSession):
    """Test metrics querying through API."""
    # Create test metrics data
    await test_db_session.execute(
        "INSERT INTO metric_snapshots (metric_name, value, timestamp, source) VALUES "
        "('cpu_usage', 85.5, datetime('now'), 'system'), "
        "('memory_usage', 72.3, datetime('now'), 'system')"
    )
    await test_db_session.commit()

    # Query metrics
    response = client.post("/metrics", json={"query": "cpu metrics"})
    assert response.status_code == 200

    data = response.json()
    assert "metrics" in data
    assert len(data["metrics"]) > 0


def test_health_endpoint_integration(client):
    """Test health endpoint returns proper status."""
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert "database" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_concurrent_chat_sessions(client, test_db_session: AsyncSession):
    """Test multiple concurrent chat sessions."""
    # Send multiple chat messages
    responses = []
    for i in range(3):
        response = client.post("/chat", json={"message": f"Message {i}"})
        assert response.status_code == 200
        responses.append(response.json())

    # Verify all sessions are different
    session_ids = [r["session_id"] for r in responses]
    assert len(set(session_ids)) == 3  # All unique

    # Verify all messages are stored
    for session_id in session_ids:
        result = await test_db_session.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE session_id = :session_id",
            {"session_id": session_id}
        )
        count = result.scalar()
        assert count >= 1