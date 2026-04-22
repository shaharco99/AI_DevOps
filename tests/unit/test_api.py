"""Unit tests for API routes."""

import pytest
from fastapi.testclient import TestClient

from ai_devops_assistant.main import create_app


@pytest.fixture
def client():
    """Test client fixture."""
    app = create_app()
    return TestClient(app)


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "timestamp" in data


def test_chat_endpoint_requires_message(client):
    """Test chat endpoint requires message."""
    response = client.post("/chat", json={})
    assert response.status_code == 422  # Validation error


def test_run_sql_endpoint_requires_query(client):
    """Test SQL endpoint requires query."""
    response = client.post("/run_sql", json={})
    assert response.status_code == 422  # Validation error


def test_analyze_logs_endpoint_requires_query(client):
    """Test log analysis endpoint requires query."""
    response = client.post("/analyze_logs", json={})
    assert response.status_code == 422  # Validation error


def test_metrics_endpoint_requires_query(client):
    """Test metrics endpoint requires query."""
    response = client.post("/metrics", json={})
    assert response.status_code == 422  # Validation error