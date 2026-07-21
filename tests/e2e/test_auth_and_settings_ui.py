"""Browser tests for the four UI gaps found during manual testing.

Each class here corresponds to one defect:

1. The page could not authenticate at all — it only ever *read* the CSRF cookie
   and never called /auth/session, so against a deployment with an API key set
   every request 401'd with no way to log in.
2. The CSRF token was minted, documented as protecting the streaming POST, and
   then never verified by any endpoint.
3. /chat/sessions/{id} truncated every message to 200 characters, and the UI
   restores conversations from it — so reopening a chat silently mangled it.
4. The model picker was populated but never read: no change listener, and the
   selection was not in the request body.

``settings.API_KEY`` is read per request by the auth dependency, so a test can
switch the live server between demo mode and protected mode by patching it — no
second server needed.
"""

import re
from unittest.mock import patch

import pytest
from playwright.async_api import Page, expect

from ai_devops_assistant.config.settings import settings

from .conftest import done_event

pytestmark = [pytest.mark.e2e, pytest.mark.slow]

API_KEY = "test-key-for-e2e"


async def open_ui(page: Page, base_url: str) -> None:
    await page.goto(f"{base_url}/ui/", wait_until="load")
    await page.wait_for_selector("#input", state="visible")


class TestDemoModeNeedsNoLogin:
    """With no API key configured the deployment is open; do not nag the user."""

    async def test_no_login_overlay_appears(self, page: Page, base_url: str):
        with patch.object(settings, "API_KEY", ""):
            await open_ui(page, base_url)
            await page.wait_for_timeout(500)
            assert await page.locator("#login-overlay").count() == 0

    async def test_the_page_does_not_spend_the_auth_rate_limit_on_load(
        self, page: Page, base_url: str
    ):
        """/auth/session allows 10/minute per IP because it takes a credential.

        Bootstrapping a session on every page load spent that budget on visitors
        who needed no session at all: ten reloads, or a few colleagues behind one
        NAT address, and the UI locked itself out.
        """
        calls: list[str] = []
        page.on(
            "request",
            lambda r: calls.append(r.url) if "/auth/session" in r.url else None,
        )
        with patch.object(settings, "API_KEY", ""):
            await open_ui(page, base_url)
            await page.wait_for_timeout(500)

        assert calls == [], f"page load hit the rate-limited auth endpoint: {calls}"


class TestProtectedDeploymentCanLogIn:
    """The gap that made the UI unusable outside demo mode."""

    async def test_a_login_prompt_appears_when_the_server_requires_a_key(
        self, page: Page, base_url: str
    ):
        with patch.object(settings, "API_KEY", API_KEY):
            await open_ui(page, base_url)
            await expect(page.locator("#login-overlay")).to_be_visible(timeout=10000)
            await expect(page.locator("#login-key")).to_be_visible()

    async def test_a_wrong_key_is_rejected_and_the_prompt_stays(self, page: Page, base_url: str):
        with patch.object(settings, "API_KEY", API_KEY):
            await open_ui(page, base_url)
            await expect(page.locator("#login-overlay")).to_be_visible(timeout=10000)

            await page.fill("#login-key", "definitely-wrong")
            await page.click("#login-submit")

            await expect(page.locator(".login-error")).to_contain_text("not accepted")
            await expect(page.locator("#login-overlay")).to_be_visible()

    async def test_the_right_key_dismisses_the_prompt_and_sets_a_session(
        self, page: Page, base_url: str
    ):
        with patch.object(settings, "API_KEY", API_KEY):
            await open_ui(page, base_url)
            await expect(page.locator("#login-overlay")).to_be_visible(timeout=10000)

            await page.fill("#login-key", API_KEY)
            await page.click("#login-submit")

            await expect(page.locator("#login-overlay")).to_have_count(0, timeout=10000)

            cookies = await page.context.cookies()
            names = {c["name"] for c in cookies}
            assert "ai_devops_session" in names, "no session cookie was issued"
            assert "ai_devops_csrf" in names, "no CSRF cookie was issued"

    async def test_the_session_cookie_is_not_readable_from_javascript(
        self, page: Page, base_url: str
    ):
        """HttpOnly is the whole point: an XSS on the page must not lift it."""
        with patch.object(settings, "API_KEY", API_KEY):
            await open_ui(page, base_url)
            await expect(page.locator("#login-overlay")).to_be_visible(timeout=10000)
            await page.fill("#login-key", API_KEY)
            await page.click("#login-submit")
            await expect(page.locator("#login-overlay")).to_have_count(0, timeout=10000)

            visible = await page.evaluate("() => document.cookie")

        assert "ai_devops_session" not in visible, "session cookie is readable by JS"
        # The CSRF token is readable on purpose; the client has to echo it back.
        assert "ai_devops_csrf" in visible

    async def test_the_api_key_is_never_written_into_the_page(self, page: Page, base_url: str):
        """The key is exchanged and dropped; it must not linger in storage."""
        with patch.object(settings, "API_KEY", API_KEY):
            await open_ui(page, base_url)
            await expect(page.locator("#login-overlay")).to_be_visible(timeout=10000)
            await page.fill("#login-key", API_KEY)
            await page.click("#login-submit")
            await expect(page.locator("#login-overlay")).to_have_count(0, timeout=10000)

            stored = await page.evaluate(
                "() => JSON.stringify({l: {...localStorage}, s: {...sessionStorage}})"
            )
            cookies = await page.context.cookies()

        assert API_KEY not in stored, "API key was persisted in web storage"
        assert all(API_KEY not in c["value"] for c in cookies), "API key was put in a cookie"


class TestCsrfIsActuallyEnforced:
    """The token was minted and documented, but no endpoint ever checked it."""

    async def _login(self, page: Page, base_url: str) -> None:
        await open_ui(page, base_url)
        await expect(page.locator("#login-overlay")).to_be_visible(timeout=10000)
        await page.fill("#login-key", API_KEY)
        await page.click("#login-submit")
        await expect(page.locator("#login-overlay")).to_have_count(0, timeout=10000)

    async def test_a_cookie_authenticated_post_without_the_header_is_refused(
        self, page: Page, base_url: str
    ):
        """What a cross-site form submission looks like: cookie, no header."""
        with patch.object(settings, "API_KEY", API_KEY):
            await self._login(page, base_url)
            status = await page.evaluate(
                """async () => {
                    const r = await fetch('/chat/stream', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: 'hi', session_id: 'csrf-probe' }),
                        credentials: 'same-origin',
                    });
                    return r.status;
                }"""
            )
        assert status == 403, f"expected 403 without a CSRF header, got {status}"

    async def test_a_wrong_csrf_token_is_refused(self, page: Page, base_url: str):
        with patch.object(settings, "API_KEY", API_KEY):
            await self._login(page, base_url)
            status = await page.evaluate(
                """async () => {
                    const r = await fetch('/chat/stream', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRF-Token': 'not-the-real-token',
                        },
                        body: JSON.stringify({ message: 'hi', session_id: 'csrf-probe' }),
                        credentials: 'same-origin',
                    });
                    return r.status;
                }"""
            )
        assert status == 403, f"expected 403 for a forged CSRF token, got {status}"

    async def test_the_real_token_from_the_cookie_is_accepted(
        self, page: Page, base_url: str, agent_events
    ):
        agent_events(done_event())
        with patch.object(settings, "API_KEY", API_KEY):
            await self._login(page, base_url)
            status = await page.evaluate(
                """async () => {
                    const token = document.cookie
                        .match(/(?:^|; )ai_devops_csrf=([^;]*)/)[1];
                    const r = await fetch('/chat/stream', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRF-Token': decodeURIComponent(token),
                        },
                        body: JSON.stringify({ message: 'hi', session_id: 'csrf-ok' }),
                        credentials: 'same-origin',
                    });
                    return r.status;
                }"""
            )
        assert status == 200, f"a correctly-signed request was refused: {status}"

    async def test_the_ui_itself_can_still_send_a_message_once_logged_in(
        self, page: Page, base_url: str, agent_events
    ):
        """The end-to-end proof that CSRF enforcement did not break the UI."""
        agent_events(done_event("Working fine"))
        with patch.object(settings, "API_KEY", API_KEY):
            await self._login(page, base_url)
            await page.fill("#input", "does this still work?")
            await page.press("#input", "Enter")
            await expect(page.locator(".message.assistant .message-body")).to_contain_text(
                "Working fine", timeout=15000
            )


class TestHistoryIsRestoredIntact:
    """/chat/sessions/{id} used to return content[:200].

    That was harmless while the endpoint was only for debugging, but the UI
    restores a conversation from it when a session is clicked in the sidebar. So
    reopening a chat quietly replaced every answer longer than 200 characters
    with a fragment, and nothing indicated anything was missing.
    """

    # Long enough that the old 200-character cut lands in the middle, with a
    # marker at each end so a truncated restore cannot pass.
    LONG_ANSWER = (
        "START-OF-ANSWER " + ("filler words to pad this reply out. " * 12) + "END-OF-ANSWER"
    )

    async def test_the_full_answer_comes_back_from_the_history_endpoint(
        self, page: Page, base_url: str, agent_events
    ):
        assert len(self.LONG_ANSWER) > 400, "fixture must exceed the old truncation point"
        agent_events(done_event(self.LONG_ANSWER))
        session_id = "history-probe-e2e"

        with patch.object(settings, "API_KEY", ""):
            await open_ui(page, base_url)
            # Drive the stream directly so the session id is known and stable.
            await page.evaluate(
                """async (sid) => {
                    const { streamPost } = await import('/ui/js/sse.js');
                    await streamPost('/chat/stream',
                        { message: 'tell me everything', session_id: sid },
                        () => {});
                }""",
                session_id,
            )
            restored = await page.evaluate(
                """async (sid) => {
                    const r = await fetch(`/chat/sessions/${sid}`, {
                        credentials: 'same-origin',
                    });
                    if (!r.ok) return { error: r.status };
                    const data = await r.json();
                    return { contents: (data.messages ?? []).map(m => m.content) };
                }""",
                session_id,
            )

        assert "error" not in restored, f"history fetch failed: {restored}"
        assistant = [c for c in restored["contents"] if "START-OF-ANSWER" in c]
        assert assistant, f"stored answer not found in {restored['contents']}"
        assert "END-OF-ANSWER" in assistant[0], "history came back truncated"
        assert len(assistant[0]) == len(self.LONG_ANSWER)


class TestModelPickerIsWiredUp:
    """The picker was populated from /models but its value was never sent."""

    async def test_the_picker_is_populated(self, page: Page, base_url: str):
        with patch.object(settings, "API_KEY", ""):
            await open_ui(page, base_url)
            await expect(page.locator("#model option").first).to_be_attached(timeout=10000)

    async def test_the_selected_model_reaches_the_agent(
        self, page: Page, base_url: str, agent_events
    ):
        stream = agent_events(done_event())
        with patch.object(settings, "API_KEY", ""):
            await open_ui(page, base_url)
            await expect(page.locator("#model option").first).to_be_attached(timeout=10000)

            chosen = await page.evaluate(
                """() => {
                    const picker = document.getElementById('model');
                    picker.selectedIndex = picker.options.length - 1;
                    return picker.value;
                }"""
            )
            await page.fill("#input", "which model are you?")
            await page.press("#input", "Enter")
            await expect(page.locator(".message.assistant")).to_contain_text(
                "All good", timeout=15000
            )

        assert stream.calls, "the agent was never called"
        assert stream.calls[-1].get("model") == chosen, (
            f"picker showed {chosen!r} but the agent received " f"{stream.calls[-1].get('model')!r}"
        )

    async def test_the_request_body_carries_the_model(
        self, page: Page, base_url: str, agent_events
    ):
        agent_events(done_event())
        bodies: list[str] = []
        page.on(
            "request",
            lambda r: bodies.append(r.post_data or "") if "/chat/stream" in r.url else None,
        )
        with patch.object(settings, "API_KEY", ""):
            await open_ui(page, base_url)
            await expect(page.locator("#model option").first).to_be_attached(timeout=10000)
            await page.fill("#input", "hello")
            await page.press("#input", "Enter")
            await expect(page.locator(".message.assistant")).to_contain_text(
                "All good", timeout=15000
            )

        assert bodies, "no /chat/stream request was made"
        assert re.search(
            r'"model"\s*:\s*"[^"]+"', bodies[-1]
        ), f"model missing from request body: {bodies[-1]}"
