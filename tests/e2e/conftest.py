"""Fixtures for the browser end-to-end tests.

These tests drive a real Chromium against a real uvicorn server, because that is
the only place several of the UI's bugs are observable at all. The parser unit
tests in ``tests/js`` passed for months while the streaming UI was completely
dead: they fed the parser LF-framed input, and the server sends CRLF. Nothing
short of a browser talking to the real SSE endpoint catches that class of bug.

What is real here and what is faked:

- Real: the FastAPI app, the static assets, the SSE encoder, the browser, and
  every line of the shipped JavaScript.
- Faked: the agent. Its events are scripted, so the tests are deterministic and
  finish in milliseconds instead of waiting on a local model.

The server runs in a thread inside the test process on purpose — patching the
agent has to be visible to the request handler, and that only works if they
share an interpreter.

Playwright's *async* API is used rather than the sync one. The sync API refuses
to run inside a thread that already has an asyncio loop, and this suite runs
under ``asyncio_mode = "auto"``, so the sync API deadlocks on first use.
"""

import socket
import threading
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import closing
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

pytest.importorskip(
    "playwright.async_api",
    reason="browser tests need the 'browser' extra: pip install -e '.[browser]' "
    "&& playwright install chromium",
)

from playwright.async_api import Browser, Page, async_playwright  # noqa: E402

from ai_devops_assistant.agents.events import AgentEvent, EventType  # noqa: E402
from ai_devops_assistant.main import create_app  # noqa: E402


def _free_port() -> int:
    """Bind port 0 to let the OS pick a free port, then hand it over."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="session")
def server_port() -> int:
    return _free_port()


@pytest.fixture(scope="session")
def base_url(server_port: int) -> str:
    return f"http://127.0.0.1:{server_port}"


@pytest.fixture(scope="session", autouse=True)
def live_server(server_port: int, base_url: str) -> Iterator[str]:
    """Run the real app under uvicorn in a background thread for the session."""
    import httpx
    import uvicorn

    config = uvicorn.Config(
        create_app(),
        host="127.0.0.1",
        port=server_port,
        log_level="warning",
        # The tests assert on cookie behaviour; over plain HTTP a Secure cookie
        # would never be stored and every session test would fail confusingly.
        forwarded_allow_ips="*",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 30
    while time.time() < deadline:
        if server.started:
            try:
                if httpx.get(f"{base_url}/health", timeout=2).status_code == 200:
                    break
            except Exception:  # noqa: BLE001 - still booting
                pass
        time.sleep(0.05)
    else:
        raise RuntimeError("live server did not become healthy in time")

    yield base_url

    server.should_exit = True
    thread.join(timeout=10)


@pytest_asyncio.fixture
async def page() -> AsyncIterator[Page]:
    """A fresh browser and page per test.

    Function-scoped on purpose. Playwright objects belong to the event loop that
    created them, and pytest-asyncio gives each test its own loop, so a
    session-scoped browser would be driven from a loop it was not created on and
    hang. Launching per test costs a fraction of a second and buys a guaranteed
    clean profile: no shared cookies, and no shared HTTP cache — a cached ES
    module is exactly what makes an already-fixed asset still look broken.
    """
    async with async_playwright() as playwright:
        browser: Browser = await playwright.chromium.launch()
        context = await browser.new_context()
        new_page = await context.new_page()

        errors: list[str] = []
        new_page.on("pageerror", lambda exc: errors.append(str(exc)))
        new_page.on(
            "console",
            lambda msg: errors.append(msg.text) if msg.type == "error" else None,
        )
        new_page.console_errors = errors  # type: ignore[attr-defined]

        yield new_page

        await context.close()
        await browser.close()


def fake_stream(*events: AgentEvent):
    """Build a chat_stream replacement that yields the given events."""

    async def _stream(*args, **kwargs):
        # Recorded so tests can assert on what the route forwarded, which is how
        # the model-picker test proves the selection reaches the agent.
        _stream.calls.append(kwargs)
        for event in events:
            yield event

    _stream.calls = []
    return _stream


def done_event(message: str = "All good", session_id: str = "s1") -> AgentEvent:
    """A terminal DONE event with the fields the route expects to find."""
    return AgentEvent(
        type=EventType.DONE,
        data={
            "content": message,
            "message": message,
            "tool_calls": [],
            "tool_results": {},
            "thinking": "",
            "metadata": {},
            "confidence_score": 0.9,
            "reasoning_steps": [],
            "session_id": session_id,
        },
    )


@pytest.fixture
def agent_events():
    """Install a fake agent whose chat_stream yields the supplied events.

    Returns the installed stream so a test can inspect the kwargs it received.
    """
    installed = {}

    def _install(*events: AgentEvent):
        stream = fake_stream(*events)
        agent = MagicMock()
        agent.chat_stream = stream
        installed["stream"] = stream
        patcher = patch(
            "ai_devops_assistant.api.routes.chat.get_agent",
            new=AsyncMock(return_value=agent),
        )
        patcher.start()
        installed["patcher"] = patcher
        return stream

    yield _install

    if "patcher" in installed:
        installed["patcher"].stop()
