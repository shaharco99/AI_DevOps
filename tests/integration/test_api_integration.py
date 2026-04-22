"""Integration tests for API endpoint behavior."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from ai_devops_assistant.main import create_app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(create_app())


@pytest.mark.asyncio
async def test_full_chat_flow(client, monkeypatch):
    """Test chat endpoint response contract with mocked agent."""

    class FakeAgent:
        async def chat(self, message, session_id, use_rag):
            return {
                "success": True,
                "message": f"Processed: {message}",
                "tool_calls": [{"name": "pipeline_status_tool", "parameters": {"action": "get_status"}}],
                "tool_results": {"pipeline_status_tool": {"success": True}},
                "thinking": "Checking CI/CD run history.",
            }

    async def fake_get_agent(_session):
        return FakeAgent()

    async def fake_add_chat_message(*args, **kwargs):
        return None

    monkeypatch.setattr("ai_devops_assistant.api.routes.chat.get_agent", fake_get_agent)
    monkeypatch.setattr("ai_devops_assistant.api.routes.chat.add_chat_message", fake_add_chat_message)

    response = client.post("/chat", json={"message": "Hello, check system status"})
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert data["message"].startswith("Processed:")
    assert isinstance(data.get("tool_calls"), list)


@pytest.mark.asyncio
async def test_sql_query_integration(client, monkeypatch):
    """Test SQL endpoint response contract."""

    async def fake_execute(self, query, limit=None, **kwargs):
        return {
            "success": True,
            "rows": [{"count": 2}],
            "count": 1,
        }

    monkeypatch.setattr("ai_devops_assistant.tools.sql_tool.SQLQueryTool.execute", fake_execute)

    response = client.post("/run_sql", json={"query": "SELECT COUNT(*) as count FROM application_logs"})
    assert response.status_code == 200
    data = response.json()
    assert "rows" in data
    assert data["count"] == 1


@pytest.mark.asyncio
async def test_log_analysis_integration(client, monkeypatch):
    """Test log analysis endpoint response contract."""

    async def fake_execute(self, query, log_type="application", time_range_hours=24, limit=100, **kwargs):
        return {
            "success": True,
            "logs": [
                {
                    "timestamp": datetime.now(timezone.utc),
                    "level": "ERROR",
                    "message": "Database connection failed",
                    "source": "api",
                }
            ],
        }

    monkeypatch.setattr("ai_devops_assistant.tools.log_tool.LogAnalysisTool.execute", fake_execute)

    response = client.post("/analyze_logs", json={"query": "error logs"})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["level"] == "ERROR"


@pytest.mark.asyncio
async def test_metrics_integration(client, monkeypatch):
    """Test metrics endpoint response contract."""

    async def fake_execute(self, query, duration="1h", **kwargs):
        return {
            "success": True,
            "time_series": [
                {
                    "metric_name": "cpu_usage",
                    "labels": {"service": "api"},
                    "values": [{"timestamp": 1713772800, "value": 85.5}],
                }
            ],
            "query_time_ms": 12.3,
        }

    monkeypatch.setattr("ai_devops_assistant.tools.metrics_tool.MetricsTool.execute", fake_execute)

    response = client.post("/metrics", json={"query": "cpu_usage"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["time_series"]) == 1
    assert data["time_series"][0]["metric_name"] == "cpu_usage"


def test_health_endpoint_integration(client):
    """Test health endpoint returns proper status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "environment" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_concurrent_chat_sessions(client, monkeypatch):
    """Test unique session IDs across multiple chat requests."""

    class FakeAgent:
        async def chat(self, message, session_id, use_rag):
            return {
                "success": True,
                "message": f"Processed: {message}",
                "tool_calls": [],
                "tool_results": {},
            }

    async def fake_get_agent(_session):
        return FakeAgent()

    async def fake_add_chat_message(*args, **kwargs):
        return None

    monkeypatch.setattr("ai_devops_assistant.api.routes.chat.get_agent", fake_get_agent)
    monkeypatch.setattr("ai_devops_assistant.api.routes.chat.add_chat_message", fake_add_chat_message)

    session_ids = []
    for i in range(3):
        response = client.post("/chat", json={"message": f"Message {i}"})
        assert response.status_code == 200
        session_ids.append(response.json()["session_id"])

    assert len(set(session_ids)) == 3