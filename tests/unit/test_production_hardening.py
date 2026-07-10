"""Unit tests for readiness checks, API-key auth, and LLM retry behavior."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from ai_devops_assistant.config.settings import settings
from ai_devops_assistant.main import create_app
from ai_devops_assistant.services.llm_service import LLMServiceError, OllamaService


@pytest.fixture
def client():
    """Test client fixture."""
    app = create_app()
    return TestClient(app)


# ============================================================================
# Readiness endpoint
# ============================================================================


def test_readiness_healthy(client):
    """Readiness returns 200 with per-dependency detail when all checks pass."""
    with (
        patch(
            "ai_devops_assistant.api.routes.health._check_database",
            new=AsyncMock(return_value=(True, "ok")),
        ),
        patch(
            "ai_devops_assistant.api.routes.health._check_llm",
            new=AsyncMock(return_value=(True, "ok")),
        ),
    ):
        response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"]["healthy"] is True
    assert data["checks"]["llm"]["healthy"] is True


def test_readiness_db_down_returns_503(client):
    """Readiness returns 503 when the database check fails."""
    with (
        patch(
            "ai_devops_assistant.api.routes.health._check_database",
            new=AsyncMock(return_value=(False, "connection refused")),
        ),
        patch(
            "ai_devops_assistant.api.routes.health._check_llm",
            new=AsyncMock(return_value=(True, "ok")),
        ),
    ):
        response = client.get("/health/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["checks"]["database"]["healthy"] is False


def test_liveness_stays_shallow(client):
    """Liveness must not depend on downstreams."""
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


# ============================================================================
# API-key auth
# ============================================================================


def test_auth_disabled_when_api_key_unset(client):
    """Without API_KEY configured, routes stay open (local demo mode)."""
    with patch.object(settings, "API_KEY", None):
        response = client.post("/run_sql", json={})
    # 422 = passed auth, failed body validation
    assert response.status_code == 422


def test_auth_rejects_missing_key(client):
    """With API_KEY configured, requests without the header get 401."""
    with patch.object(settings, "API_KEY", "test-key"):
        response = client.post("/run_sql", json={"query": "SELECT 1"})
    assert response.status_code == 401


def test_auth_rejects_wrong_key(client):
    """With API_KEY configured, a wrong header value gets 401."""
    with patch.object(settings, "API_KEY", "test-key"):
        response = client.post(
            "/run_sql",
            json={"query": "SELECT 1"},
            headers={"X-API-Key": "wrong"},
        )
    assert response.status_code == 401


def test_auth_accepts_valid_key(client):
    """A valid X-API-Key passes the auth dependency."""
    with patch.object(settings, "API_KEY", "test-key"):
        response = client.post("/run_sql", json={}, headers={"X-API-Key": "test-key"})
    # 422 = passed auth, failed body validation
    assert response.status_code == 422


def test_health_not_behind_auth(client):
    """Health endpoints must stay unauthenticated for probes."""
    with patch.object(settings, "API_KEY", "test-key"):
        response = client.get("/health")
    assert response.status_code == 200


# ============================================================================
# LLM retry behavior
# ============================================================================


async def test_ollama_chat_retries_on_transport_error():
    """Transient transport errors are retried, then surface as LLMServiceError."""
    service = OllamaService()
    mock_post = AsyncMock(side_effect=httpx.ConnectError("boom"))
    with patch.object(service.client, "post", mock_post):
        with pytest.raises(LLMServiceError):
            await service.chat([{"role": "user", "content": "hi"}])
    assert mock_post.call_count == 3
    await service.close()


async def test_ollama_chat_no_retry_on_4xx():
    """Client errors (4xx) are not retried."""
    service = OllamaService()
    request = httpx.Request("POST", "http://test/api/chat")
    response = httpx.Response(404, request=request)
    mock_post = AsyncMock(return_value=response)
    with patch.object(service.client, "post", mock_post):
        with pytest.raises(LLMServiceError):
            await service.chat([{"role": "user", "content": "hi"}])
    assert mock_post.call_count == 1
    await service.close()


async def test_ollama_chat_succeeds_after_transient_failure():
    """A 5xx followed by a 200 succeeds via retry."""
    service = OllamaService()
    request = httpx.Request("POST", "http://test/api/chat")
    bad = httpx.Response(503, request=request)
    good = httpx.Response(200, request=request, json={"message": {"content": "hello"}})
    mock_post = AsyncMock(side_effect=[bad, good])
    with patch.object(service.client, "post", mock_post):
        result = await service.chat([{"role": "user", "content": "hi"}])
    assert result == "hello"
    assert mock_post.call_count == 2
    await service.close()
