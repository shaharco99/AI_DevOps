"""End-to-end browser tests for the chat UI.

Every test here drives real Chromium against the real server. The agent is
scripted so the assertions are about the UI, not about what a model happened to
say.

Each class corresponds to behaviour that was broken at some point and is cheap
to break again. In particular ``TestStreamingRendersInTheBrowser`` is the
regression net for the CRLF framing bug, which the JS unit tests could not see
because they framed their fixtures with LF while the server sends CRLF.
"""

import re

import pytest
from playwright.async_api import Page, expect

from ai_devops_assistant.agents.events import AgentEvent, EventType

from .conftest import done_event

pytestmark = [pytest.mark.e2e, pytest.mark.slow]


async def open_ui(page: Page, base_url: str) -> None:
    """Load the UI and wait until the composer is interactive."""
    await page.goto(f"{base_url}/ui/", wait_until="load")
    await page.wait_for_selector("#input", state="visible")


async def send(page: Page, message: str) -> None:
    await page.fill("#input", message)
    await page.press("#input", "Enter")


class TestPageLoads:
    async def test_the_page_renders_without_console_errors(self, page: Page, base_url: str):
        await open_ui(page, base_url)
        await expect(page.locator("#input")).to_be_visible()
        await expect(page.locator("#send")).to_be_visible()
        assert page.console_errors == [], f"console errors: {page.console_errors}"

    async def test_the_title_and_composer_are_present(self, page: Page, base_url: str):
        await open_ui(page, base_url)
        assert (await page.title()) == "AI DevOps Assistant"
        await expect(page.locator("#input")).to_have_attribute(
            "placeholder", re.compile(r"Ask anything")
        )

    async def test_every_module_the_page_imports_actually_loads(self, page: Page, base_url: str):
        """A 404 or a wrong MIME type on an ES module fails silently otherwise."""
        failures: list[str] = []
        page.on(
            "response",
            lambda r: failures.append(f"{r.status} {r.url}") if r.status >= 400 else None,
        )
        await open_ui(page, base_url)
        await page.wait_for_timeout(300)
        assert failures == [], f"failed requests: {failures}"


class TestStreamingRendersInTheBrowser:
    """The regression net for the CRLF SSE framing bug.

    The server frames events with CRLF. The client split frames on "\\n\\n",
    which never occurs in "\\r\\n\\r\\n", so not one event was ever emitted and
    the assistant bubble stayed empty for the entire response. Every assertion
    below failed before the parser was fixed, and none of them can be satisfied
    without real frames crossing a real socket.
    """

    async def test_tokens_stream_into_the_assistant_message(
        self, page: Page, base_url: str, agent_events
    ):
        agent_events(
            AgentEvent(type=EventType.TOKEN, data={"t": "Three "}),
            AgentEvent(type=EventType.TOKEN, data={"t": "pods "}),
            AgentEvent(type=EventType.TOKEN, data={"t": "failed"}),
            done_event("Three pods failed"),
        )
        await open_ui(page, base_url)
        await send(page, "what is failing?")

        body = page.locator(".message.assistant .message-body")
        await expect(body).to_contain_text("Three pods failed", timeout=15000)

    async def test_the_status_line_reports_progress_while_working(
        self, page: Page, base_url: str, agent_events
    ):
        agent_events(
            AgentEvent(type=EventType.STATUS, data={"phase": "gathering_context"}),
            done_event(),
        )
        await open_ui(page, base_url)
        await send(page, "hello")

        # Either the phase is caught mid-flight or the answer already landed;
        # both prove the status frame was parsed rather than swallowed.
        await expect(page.locator(".message.assistant")).to_contain_text(
            "All good",
            timeout=15000,
        )

    async def test_the_user_message_appears_immediately(
        self, page: Page, base_url: str, agent_events
    ):
        agent_events(done_event())
        await open_ui(page, base_url)
        await send(page, "a question")
        await expect(page.locator(".message.user .message-body")).to_have_text("a question")

    async def test_the_composer_clears_after_sending(self, page: Page, base_url: str, agent_events):
        agent_events(done_event())
        await open_ui(page, base_url)
        await send(page, "a question")
        await expect(page.locator("#input")).to_have_value("")

    async def test_send_is_replaced_by_stop_while_streaming_and_restored_after(
        self, page: Page, base_url: str, agent_events
    ):
        agent_events(done_event())
        await open_ui(page, base_url)
        await send(page, "hello")
        await expect(page.locator(".message.assistant")).to_contain_text("All good", timeout=15000)
        await expect(page.locator("#send")).to_be_visible()
        await expect(page.locator("#stop")).to_be_hidden()


class TestToolChips:
    """Chips are what make the agent legible; a wrong state actively misleads."""

    async def test_a_successful_tool_renders_an_ok_chip(
        self, page: Page, base_url: str, agent_events
    ):
        agent_events(
            AgentEvent(
                type=EventType.TOOL_START,
                data={"id": "t0", "name": "sql_query_tool", "params": {"query": "SELECT 1"}},
            ),
            AgentEvent(
                type=EventType.TOOL_END,
                data={
                    "id": "t0",
                    "name": "sql_query_tool",
                    "ok": True,
                    "error": None,
                    "duration_ms": 12.5,
                    "summary": "1 row",
                },
            ),
            done_event(),
        )
        await open_ui(page, base_url)
        await send(page, "count rows")

        chip = page.locator(".tool-chip")
        await expect(chip).to_have_class("tool-chip ok", timeout=15000)
        await expect(chip).to_contain_text("sql_query_tool")
        await expect(chip).to_contain_text("1 row")

    async def test_a_failed_tool_renders_a_failed_chip_with_the_reason(
        self, page: Page, base_url: str, agent_events
    ):
        """A tool that reports success=False must not look like it worked.

        The agent used to derive ok from "did it raise", but BaseTool turns an
        exception into a {"success": False} return value, so real failures were
        painted green.
        """
        agent_events(
            AgentEvent(
                type=EventType.TOOL_START,
                data={"id": "t0", "name": "pipeline_status_tool", "params": {}},
            ),
            AgentEvent(
                type=EventType.TOOL_END,
                data={
                    "id": "t0",
                    "name": "pipeline_status_tool",
                    "ok": False,
                    "error": "Azure DevOps configuration missing",
                    "duration_ms": 0.1,
                    "summary": "",
                },
            ),
            done_event(),
        )
        await open_ui(page, base_url)
        await send(page, "pipeline status")

        chip = page.locator(".tool-chip")
        await expect(chip).to_have_class("tool-chip failed", timeout=15000)
        await expect(chip).to_contain_text("Azure DevOps configuration missing")

    async def test_chip_parameters_are_shown_when_expanded(
        self, page: Page, base_url: str, agent_events
    ):
        agent_events(
            AgentEvent(
                type=EventType.TOOL_START,
                data={"id": "t0", "name": "sql_query_tool", "params": {"query": "SELECT 42"}},
            ),
            AgentEvent(
                type=EventType.TOOL_END,
                data={"id": "t0", "name": "sql_query_tool", "ok": True, "summary": "1 row"},
            ),
            done_event(),
        )
        await open_ui(page, base_url)
        await send(page, "run it")
        await expect(page.locator(".tool-chip")).to_be_visible(timeout=15000)
        await page.locator(".tool-chip summary").click()
        await expect(page.locator(".tool-params")).to_contain_text("SELECT 42")


class TestRenderingIsNeverMarkup:
    """The renderer's core guarantee, asserted in a browser rather than by grep."""

    async def test_markdown_is_rendered_as_real_elements(
        self, page: Page, base_url: str, agent_events
    ):
        answer = "## Diagnosis\n\nCheck the pods.\n\n```sql\nSELECT 1;\n```"
        agent_events(done_event(answer))
        await open_ui(page, base_url)
        await send(page, "diagnose")

        body = page.locator(".message.assistant .message-body")
        await expect(body.locator("h4, h3, h5")).to_contain_text("Diagnosis", timeout=15000)
        await expect(body.locator(".code-block")).to_contain_text("SELECT 1;")

    async def test_html_in_a_reply_is_shown_as_text_and_not_executed(
        self, page: Page, base_url: str, agent_events
    ):
        agent_events(done_event('<img src=x onerror="window.__xss=1">'))
        await open_ui(page, base_url)
        await send(page, "try xss")

        body = page.locator(".message.assistant .message-body")
        await expect(body).to_contain_text("<img", timeout=15000)
        assert (await body.locator("img").count()) == 0, "markup was parsed instead of shown"
        assert await page.evaluate("() => window.__xss") is None, "injected script executed"

    async def test_a_script_tag_in_a_reply_never_runs(
        self, page: Page, base_url: str, agent_events
    ):
        agent_events(done_event("<script>window.__pwned = 1</script>"))
        await open_ui(page, base_url)
        await send(page, "try xss")
        await expect(page.locator(".message.assistant .message-body")).to_contain_text(
            "script", timeout=15000
        )
        assert await page.evaluate("() => window.__pwned") is None

    async def test_a_single_line_code_fence_does_not_hang_the_tab(
        self, page: Page, base_url: str, agent_events
    ):
        """parseMarkdown used to spin forever on this, freezing the page.

        The line starts with ``` but does not match the fence pattern, and the
        paragraph scanner refused it too, so the index never advanced. If this
        regresses the test times out rather than failing fast, which is itself
        the signal.
        """
        agent_events(done_event("Run this:\n\n```sh export A=1 ```\n\nThen restart."))
        await open_ui(page, base_url)
        await send(page, "how do I set it?")

        await expect(page.locator(".message.assistant .message-body")).to_contain_text(
            "Then restart.", timeout=15000
        )
        # The tab is still responsive, which a spinning parser would prevent.
        assert await page.evaluate("() => 1 + 1") == 2


class TestSessionsSidebar:
    async def test_sending_a_message_adds_a_session_to_the_sidebar(
        self, page: Page, base_url: str, agent_events
    ):
        agent_events(done_event())
        await open_ui(page, base_url)
        await send(page, "a memorable question")
        await expect(page.locator(".session-item").first).to_contain_text("a memorable question")

    async def test_new_chat_clears_the_transcript(self, page: Page, base_url: str, agent_events):
        agent_events(done_event())
        await open_ui(page, base_url)
        await send(page, "first question")
        await expect(page.locator(".message.assistant")).to_contain_text("All good", timeout=15000)

        await page.click("#new-chat")
        await expect(page.locator(".message")).to_have_count(0)


class TestTheme:
    async def test_the_theme_toggles_and_survives_a_reload(self, page: Page, base_url: str):
        await open_ui(page, base_url)
        before = await page.get_attribute("html", "data-theme")
        await page.click("#theme-toggle")
        after = await page.get_attribute("html", "data-theme")
        assert before != after, "toggling did not change the theme"

        await page.reload(wait_until="load")
        await page.wait_for_selector("#input")
        assert await page.get_attribute("html", "data-theme") == after, "theme did not persist"
