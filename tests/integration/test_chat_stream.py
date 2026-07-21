"""Integration tests for the SSE streaming chat endpoint.

Exercises the real HTTP surface: SSE framing, event ordering, what the endpoint
deliberately withholds from the browser, and that a stopped generation is still
persisted.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ai_devops_assistant.agents.events import AgentEvent, EventType
from ai_devops_assistant.main import create_app


def parse_sse(text: str) -> list[tuple[str, dict]]:
    """Parse an SSE response body into (event, data) pairs.

    Deliberately hand-rolled rather than reusing the server's encoder, so a bug
    in the encoder cannot make the tests pass.
    """
    events: list[tuple[str, dict]] = []
    event_name: str | None = None
    for line in text.splitlines():
        if line.startswith("event:"):
            event_name = line[len("event:") :].strip()
        elif line.startswith("data:"):
            raw = line[len("data:") :].strip()
            events.append((event_name or "message", json.loads(raw)))
            event_name = None
    return events


def fake_stream(*events: AgentEvent):
    """Build a chat_stream replacement that yields the given events."""

    async def _stream(*args, **kwargs):
        for event in events:
            yield event

    return _stream


DEFAULT_DONE = AgentEvent(
    type=EventType.DONE,
    data={
        "content": "Three pods are unhealthy",
        "message": "Three pods are unhealthy",
        "tool_calls": [{"name": "kubernetes_tool", "parameters": {"action": "list_pods"}}],
        "tool_results": {"kubernetes_tool": {"rows": [{"pod": f"p{i}"} for i in range(300)]}},
        "thinking": "checked the cluster",
        "metadata": {"task_id": "t1"},
        "confidence_score": 0.9,
        "reasoning_steps": ["checked the cluster"],
        "session_id": "s1",
    },
)


@pytest.fixture(autouse=True)
def reset_sse_app_status():
    """Reset sse-starlette's module-level shutdown Event between tests.

    AppStatus.should_exit_event is a global asyncio.Event that binds to the first
    event loop that touches it. Every TestClient creates a fresh loop, so without
    this the second streaming test in a run fails with "bound to a different
    event loop". Test-infrastructure only; nothing in production shares loops
    this way.
    """
    from sse_starlette.sse import AppStatus

    AppStatus.should_exit_event = None
    yield
    AppStatus.should_exit_event = None


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.fixture
def agent_with(monkeypatch):
    """Install a fake agent whose chat_stream yields the supplied events."""

    def _install(*events: AgentEvent):
        agent = MagicMock()
        agent.chat_stream = fake_stream(*events)
        return patch(
            "ai_devops_assistant.api.routes.chat.get_agent",
            new=AsyncMock(return_value=agent),
        )

    return _install


class TestSseFraming:
    """The wire format itself."""

    def test_returns_event_stream_content_type(self, client, agent_with):
        with agent_with(DEFAULT_DONE):
            resp = client.post("/chat/stream", json={"message": "hi", "session_id": "s1"})

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

    def test_frames_are_named_and_carry_json(self, client, agent_with):
        with agent_with(
            AgentEvent(type=EventType.STATUS, data={"phase": "planning"}),
            DEFAULT_DONE,
        ):
            resp = client.post("/chat/stream", json={"message": "hi", "session_id": "s1"})

        events = parse_sse(resp.text)
        names = [name for name, _ in events]
        assert "status" in names
        assert "done" in names
        assert dict(events)["status"] == {"phase": "planning"}

    def test_event_order_is_preserved(self, client, agent_with):
        with agent_with(
            AgentEvent(type=EventType.STATUS, data={"phase": "planning"}),
            AgentEvent(type=EventType.TOOL_START, data={"id": "tc_0", "name": "sql_query_tool"}),
            AgentEvent(type=EventType.TOOL_END, data={"id": "tc_0", "name": "sql_query_tool"}),
            AgentEvent(type=EventType.TOKEN, data={"t": "Three "}),
            AgentEvent(type=EventType.TOKEN, data={"t": "pods"}),
            DEFAULT_DONE,
        ):
            resp = client.post("/chat/stream", json={"message": "hi", "session_id": "s1"})

        names = [name for name, _ in parse_sse(resp.text)]
        assert names == ["status", "tool_start", "tool_end", "token", "token", "done"]

    def test_tokens_reassemble_in_order(self, client, agent_with):
        with agent_with(
            AgentEvent(type=EventType.TOKEN, data={"t": "Three "}),
            AgentEvent(type=EventType.TOKEN, data={"t": "pods are "}),
            AgentEvent(type=EventType.TOKEN, data={"t": "unhealthy"}),
            DEFAULT_DONE,
        ):
            resp = client.post("/chat/stream", json={"message": "hi", "session_id": "s1"})

        tokens = [d["t"] for name, d in parse_sse(resp.text) if name == "token"]
        assert "".join(tokens) == "Three pods are unhealthy"


class TestPayloadTrimming:
    """What the endpoint withholds from the browser, and why."""

    def test_done_event_drops_bulky_tool_results(self, client, agent_with):
        """300 rows must not be pushed down the stream; the chip shows a summary."""
        with agent_with(DEFAULT_DONE):
            resp = client.post("/chat/stream", json={"message": "hi", "session_id": "s1"})

        done = dict(parse_sse(resp.text))["done"]
        assert "tool_results" not in done
        assert "p299" not in resp.text, "raw tool rows leaked into the stream"

    def test_done_event_keeps_the_fields_the_ui_needs(self, client, agent_with):
        with agent_with(DEFAULT_DONE):
            resp = client.post("/chat/stream", json={"message": "hi", "session_id": "s1"})

        done = dict(parse_sse(resp.text))["done"]
        for key in ("message", "session_id", "tool_calls", "confidence_score"):
            assert key in done, f"UI needs {key!r}"


class TestErrorHandling:
    def test_agent_error_is_reported_without_leaking_provider_detail(self, client, agent_with):
        """Caught in a live run: agent errors carry raw upstream API detail.

        The real message included the provider name, an HTTP status, an internal
        request id and the account's billing state. None of that belongs in a
        browser; it is logged server side instead.
        """
        leaky = (
            "Anthropic chat failed: Error code: 400 - {'type': 'error', 'error': "
            "{'message': 'Your credit balance is too low to access the Anthropic API.'}, "
            "'request_id': 'req_011Cd9GDKiRhhhCxkGndnPqe'}"
        )
        with agent_with(AgentEvent(type=EventType.ERROR, data={"message": leaky})):
            resp = client.post("/chat/stream", json={"message": "hi", "session_id": "s1"})

        assert resp.status_code == 200, "errors stream as events, not HTTP failures"
        error = dict(parse_sse(resp.text))["error"]
        assert error["message"] == "The assistant could not complete this request."
        for secret in ("Anthropic", "credit balance", "req_011", "400"):
            assert secret not in resp.text, f"{secret!r} leaked to the client"

    def test_error_event_preserves_the_recoverable_flag(self, client, agent_with):
        with agent_with(
            AgentEvent(type=EventType.ERROR, data={"message": "x", "recoverable": True})
        ):
            resp = client.post("/chat/stream", json={"message": "hi", "session_id": "s1"})

        assert dict(parse_sse(resp.text))["error"]["recoverable"] is True

    def test_unexpected_exception_becomes_an_error_event(self, client):
        agent = MagicMock()

        async def _boom(*args, **kwargs):
            raise RuntimeError("kaboom")
            yield  # pragma: no cover - makes this an async generator

        agent.chat_stream = _boom
        with patch(
            "ai_devops_assistant.api.routes.chat.get_agent",
            new=AsyncMock(return_value=agent),
        ):
            resp = client.post("/chat/stream", json={"message": "hi", "session_id": "s1"})

        error = dict(parse_sse(resp.text))["error"]
        assert error["message"] == "Internal server error"
        assert "kaboom" not in resp.text, "internal detail must not leak to the client"


class TestPersistence:
    """History must survive a stopped or failed generation."""

    def test_user_message_is_stored_before_streaming(self, client, agent_with):
        with (
            agent_with(DEFAULT_DONE),
            patch(
                "ai_devops_assistant.api.routes.chat.add_chat_message", new=AsyncMock()
            ) as mock_store,
        ):
            client.post("/chat/stream", json={"message": "which pods?", "session_id": "s1"})

        roles = [call.args[2] for call in mock_store.await_args_list]
        assert roles[0] == "user", "user message must be persisted first"
        assert mock_store.await_args_list[0].args[3] == "which pods?"

    def test_assistant_reply_is_stored_after_streaming(self, client, agent_with):
        with (
            agent_with(DEFAULT_DONE),
            patch(
                "ai_devops_assistant.api.routes.chat.add_chat_message", new=AsyncMock()
            ) as mock_store,
        ):
            client.post("/chat/stream", json={"message": "hi", "session_id": "s1"})

        roles = [call.args[2] for call in mock_store.await_args_list]
        assert roles == ["user", "assistant"]
        assert mock_store.await_args_list[1].args[3] == "Three pods are unhealthy"

    def test_partial_reply_is_persisted_when_the_stream_ends_early(self, client):
        """A generation stopped after some tokens must not vanish from history."""
        agent = MagicMock()

        async def _partial(*args, **kwargs):
            yield AgentEvent(type=EventType.TOKEN, data={"t": "partial "})
            yield AgentEvent(type=EventType.TOKEN, data={"t": "answer"})
            raise RuntimeError("connection lost")

        agent.chat_stream = _partial
        with (
            patch(
                "ai_devops_assistant.api.routes.chat.get_agent",
                new=AsyncMock(return_value=agent),
            ),
            patch(
                "ai_devops_assistant.api.routes.chat.add_chat_message", new=AsyncMock()
            ) as mock_store,
        ):
            client.post("/chat/stream", json={"message": "hi", "session_id": "s1"})

        stored = {call.args[2]: call.args[3] for call in mock_store.await_args_list}
        assert stored.get("assistant") == "partial answer"

    def test_persistence_failure_does_not_break_the_stream(self, client, agent_with):
        """A DB outage should degrade history, not the user's response."""
        with (
            agent_with(DEFAULT_DONE),
            patch(
                "ai_devops_assistant.api.routes.chat.add_chat_message",
                new=AsyncMock(side_effect=Exception("db down")),
            ),
        ):
            resp = client.post("/chat/stream", json={"message": "hi", "session_id": "s1"})

        assert resp.status_code == 200
        assert "done" in [name for name, _ in parse_sse(resp.text)]

    def test_tools_used_are_recorded_without_duplicates(self, client, agent_with):
        with (
            agent_with(
                AgentEvent(type=EventType.TOOL_END, data={"id": "tc_0", "name": "kubernetes_tool"}),
                DEFAULT_DONE,
            ),
            patch(
                "ai_devops_assistant.api.routes.chat.add_chat_message", new=AsyncMock()
            ) as mock_store,
        ):
            client.post("/chat/stream", json={"message": "hi", "session_id": "s1"})

        assistant_call = mock_store.await_args_list[1]
        assert assistant_call.kwargs["tools_used"] == ["kubernetes_tool"]


class TestSessionHandling:
    def test_session_id_is_generated_when_absent(self, client, agent_with):
        with agent_with(DEFAULT_DONE):
            resp = client.post("/chat/stream", json={"message": "hi"})

        assert resp.status_code == 200

    def test_message_is_required(self, client):
        resp = client.post("/chat/stream", json={"session_id": "s1"})
        assert resp.status_code == 422


class TestNonStreamingRouteUnchanged:
    """The streaming endpoint must not have disturbed /chat."""

    def test_chat_route_still_exists_and_validates(self, client):
        resp = client.post("/chat", json={})
        assert resp.status_code == 422

    def test_both_routes_are_registered(self, client):
        paths = {r.path for r in client.app.routes if hasattr(r, "path")}
        assert "/chat" in paths
        assert "/chat/stream" in paths
