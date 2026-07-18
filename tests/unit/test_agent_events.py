"""Unit tests for agent event streaming.

Covers agents/events.py and DevOpsAgent.chat_stream(), plus the invariant that
chat() and chat_stream() cannot disagree — chat() is implemented by draining the
stream, and these tests are what stop the two from being forked later.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_devops_assistant.agents.agent import DevOpsAgent, _summarise_tool_result
from ai_devops_assistant.agents.events import AgentEvent, EventType, error_event, status_event


class TestAgentEvent:
    """The event value type and its wire format."""

    def test_to_sse_dict_uses_string_event_name(self):
        event = AgentEvent(type=EventType.TOKEN, data={"t": "hi"})
        assert event.to_sse_dict() == {"event": "token", "data": {"t": "hi"}}

    def test_done_and_error_are_terminal(self):
        assert AgentEvent(type=EventType.DONE).is_terminal
        assert AgentEvent(type=EventType.ERROR).is_terminal

    def test_progress_events_are_not_terminal(self):
        for kind in (
            EventType.STATUS,
            EventType.RAG,
            EventType.PLAN,
            EventType.TOOL_START,
            EventType.TOOL_END,
            EventType.TOKEN,
        ):
            assert not AgentEvent(type=kind).is_terminal, kind

    def test_event_type_serialises_as_its_wire_name(self):
        # str-valued enum, so json.dumps and f-strings produce the wire name.
        assert EventType.TOOL_START == "tool_start"
        assert f"{EventType.DONE.value}" == "done"

    def test_status_helper(self):
        assert status_event("planning").data == {"phase": "planning"}

    def test_error_helper_defaults_to_unrecoverable(self):
        event = error_event("boom")
        assert event.type is EventType.ERROR
        assert event.data == {"message": "boom", "recoverable": False}


class TestSummariseToolResult:
    """tool_end carries a summary, never the raw payload."""

    def test_none_is_empty(self):
        assert _summarise_tool_result(None) == ""

    def test_row_lists_are_counted_not_inlined(self):
        result = {"rows": [{"id": i} for i in range(500)]}
        assert _summarise_tool_result(result) == "500 rows"

    def test_single_row_is_singular(self):
        assert _summarise_tool_result({"rows": [{"id": 1}]}) == "1 row"

    def test_empty_row_list_is_plural(self):
        assert _summarise_tool_result({"rows": []}) == "0 rows"

    def test_long_text_is_truncated(self):
        summary = _summarise_tool_result("x" * 10_000)
        assert len(summary) <= 201
        assert summary.endswith("…")

    def test_short_text_is_preserved_exactly(self):
        assert _summarise_tool_result("all good") == "all good"


class TestMessageBoundary:
    """The final-response prompt must keep instructions and data separate.

    It used to concatenate the system prompt, retrieved context and tool output
    into a single user message. Tool output now travels fenced in
    _untrusted_sections (see agents/fencing.py), so it is no longer a parameter
    here at all.
    """

    def test_system_prompt_is_its_own_message(self):
        from ai_devops_assistant.agents.agent import AgentTask

        agent = DevOpsAgent()
        messages = agent._build_response_messages(
            AgentTask(description="which pods are failing?"),
            context="conversation history",
            system_prompt="You are a DevOps assistant.",
        )

        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a DevOps assistant."
        assert messages[-1]["role"] == "user"

    def test_untrusted_content_is_a_separate_message_from_the_request(self):
        from ai_devops_assistant.agents.agent import AgentTask

        agent = DevOpsAgent()
        agent._untrusted_sections = [("retrieved document", "UNTRUSTED DOC")]
        messages = agent._build_response_messages(
            AgentTask(description="q"), context="", system_prompt="SYSTEM RULES"
        )

        assert "UNTRUSTED DOC" not in messages[0]["content"], "never in the system turn"
        assert any("UNTRUSTED DOC" in m["content"] for m in messages[1:])

    def test_empty_context_is_omitted_cleanly(self):
        from ai_devops_assistant.agents.agent import AgentTask

        agent = DevOpsAgent()
        agent._untrusted_sections = []
        messages = agent._build_response_messages(
            AgentTask(description="just a question"), "", "SYSTEM"
        )
        assert "Context Information" not in messages[-1]["content"]
        assert [m["role"] for m in messages] == ["system", "user"]


def _mock_agent_deps(chat_side_effect=None, chat_return="Final answer"):
    """Patch the agent's three collaborators. Returns the patch context managers."""
    llm = AsyncMock()
    llm.health_check.return_value = True
    if chat_side_effect is not None:
        llm.chat.side_effect = chat_side_effect
    else:
        llm.chat.return_value = chat_return
    return llm


class TestChatStream:
    """chat_stream() event sequence."""

    @pytest.fixture
    def agent(self):
        return DevOpsAgent()

    async def _collect(self, agent, message="Hello", **kwargs):
        return [e async for e in agent.chat_stream(message, session_id="s1", **kwargs)]

    @pytest.mark.asyncio
    async def test_emits_exactly_one_terminal_event_last(self, agent):
        with (
            patch("ai_devops_assistant.agents.agent.get_llm_service") as mock_llm,
            patch("ai_devops_assistant.agents.agent.get_tool_executor") as mock_exec,
            patch("ai_devops_assistant.agents.agent.get_session_manager") as mock_sm,
        ):
            mock_llm.return_value = _mock_agent_deps()
            mock_exec.return_value = MagicMock()
            mock_sm.return_value = MagicMock()
            await agent.initialize()

            events = await self._collect(agent)

        terminals = [e for e in events if e.is_terminal]
        assert len(terminals) == 1, "exactly one terminal event"
        assert events[-1].is_terminal, "terminal event must be last"

    @pytest.mark.asyncio
    async def test_successful_run_ends_in_done_with_the_response(self, agent):
        with (
            patch("ai_devops_assistant.agents.agent.get_llm_service") as mock_llm,
            patch("ai_devops_assistant.agents.agent.get_tool_executor") as mock_exec,
            patch("ai_devops_assistant.agents.agent.get_session_manager") as mock_sm,
        ):
            mock_llm.return_value = _mock_agent_deps(chat_return="All three pods are healthy")
            mock_exec.return_value = MagicMock()
            mock_sm.return_value = MagicMock()
            await agent.initialize()

            events = await self._collect(agent, "are the pods ok?")

        done = events[-1]
        assert done.type is EventType.DONE
        assert "All three pods are healthy" in done.data["message"]
        assert done.data["session_id"] == "s1"

    @pytest.mark.asyncio
    async def test_done_payload_is_json_safe(self, agent):
        """The DONE event goes out over SSE, so it must serialise."""
        import json

        with (
            patch("ai_devops_assistant.agents.agent.get_llm_service") as mock_llm,
            patch("ai_devops_assistant.agents.agent.get_tool_executor") as mock_exec,
            patch("ai_devops_assistant.agents.agent.get_session_manager") as mock_sm,
        ):
            mock_llm.return_value = _mock_agent_deps()
            mock_exec.return_value = MagicMock()
            mock_sm.return_value = MagicMock()
            await agent.initialize()

            events = await self._collect(agent)

        # Must not raise. The internal AgentResponse is unwrapped by chat_stream.
        json.dumps(events[-1].data)

    @pytest.mark.asyncio
    async def test_status_and_token_events_precede_done(self, agent):
        with (
            patch("ai_devops_assistant.agents.agent.get_llm_service") as mock_llm,
            patch("ai_devops_assistant.agents.agent.get_tool_executor") as mock_exec,
            patch("ai_devops_assistant.agents.agent.get_session_manager") as mock_sm,
        ):
            mock_llm.return_value = _mock_agent_deps(chat_return="a fairly long answer here")
            mock_exec.return_value = MagicMock()
            mock_sm.return_value = MagicMock()
            await agent.initialize()

            events = await self._collect(agent)

        types = [e.type for e in events]
        assert EventType.STATUS in types
        assert EventType.TOKEN in types
        assert types.index(EventType.TOKEN) < types.index(EventType.DONE)

    @pytest.mark.asyncio
    async def test_tokens_reassemble_into_the_final_message(self, agent):
        with (
            patch("ai_devops_assistant.agents.agent.get_llm_service") as mock_llm,
            patch("ai_devops_assistant.agents.agent.get_tool_executor") as mock_exec,
            patch("ai_devops_assistant.agents.agent.get_session_manager") as mock_sm,
        ):
            answer = "Three pods are in CrashLoopBackOff in the prod namespace."
            mock_llm.return_value = _mock_agent_deps(chat_return=answer)
            mock_exec.return_value = MagicMock()
            mock_sm.return_value = MagicMock()
            await agent.initialize()

            events = await self._collect(agent)

        streamed = "".join(e.data["t"] for e in events if e.type is EventType.TOKEN)
        assert streamed.strip() == events[-1].data["message"].strip()

    @pytest.mark.asyncio
    async def test_failure_yields_error_event_and_does_not_raise(self, agent):
        with (
            patch("ai_devops_assistant.agents.agent.get_llm_service") as mock_llm,
            patch("ai_devops_assistant.agents.agent.get_tool_executor") as mock_exec,
            patch("ai_devops_assistant.agents.agent.get_session_manager") as mock_sm,
        ):
            mock_llm.return_value = _mock_agent_deps(chat_side_effect=Exception("LLM exploded"))
            mock_exec.return_value = MagicMock()
            mock_sm.return_value = MagicMock()
            await agent.initialize()

            events = await self._collect(agent)

        assert events[-1].type is EventType.ERROR
        assert "LLM exploded" in events[-1].data["message"]


class TestChatStreamParity:
    """chat() must agree with chat_stream(); it is implemented by draining it."""

    @pytest.fixture
    def agent(self):
        return DevOpsAgent()

    @pytest.mark.asyncio
    async def test_chat_returns_the_done_payload_plus_success(self, agent):
        with (
            patch("ai_devops_assistant.agents.agent.get_llm_service") as mock_llm,
            patch("ai_devops_assistant.agents.agent.get_tool_executor") as mock_exec,
            patch("ai_devops_assistant.agents.agent.get_session_manager") as mock_sm,
        ):
            mock_llm.return_value = _mock_agent_deps(chat_return="parity answer")
            mock_exec.return_value = MagicMock()
            mock_sm.return_value = MagicMock()
            await agent.initialize()

            stream_events = [e async for e in agent.chat_stream("q", session_id="s1")]

            # Fresh agent so conversation history does not differ between the runs.
            agent2 = DevOpsAgent()
            await agent2.initialize()
            chat_result = await agent2.chat("q", session_id="s1")

        done_payload = stream_events[-1].data

        # chat() is exactly the DONE payload plus success, so the key sets must
        # match. Compared as sets rather than values because these are two
        # separate runs: metadata carries a fresh task_id UUID each time.
        assert set(chat_result) == set(done_payload) | {"success"}
        assert chat_result["success"] is True

        # Every value that is not run-specific must agree.
        for key in ("content", "message", "tool_calls", "tool_results", "session_id"):
            assert chat_result[key] == done_payload[key], f"chat() disagreed on {key!r}"

    @pytest.mark.asyncio
    async def test_chat_preserves_its_documented_keys(self, agent):
        """The /chat route and its tests depend on this exact shape."""
        with (
            patch("ai_devops_assistant.agents.agent.get_llm_service") as mock_llm,
            patch("ai_devops_assistant.agents.agent.get_tool_executor") as mock_exec,
            patch("ai_devops_assistant.agents.agent.get_session_manager") as mock_sm,
        ):
            mock_llm.return_value = _mock_agent_deps()
            mock_exec.return_value = MagicMock()
            mock_sm.return_value = MagicMock()
            await agent.initialize()

            result = await agent.chat("Hello", session_id="s1")

        for key in (
            "success",
            "content",
            "message",
            "tool_calls",
            "tool_results",
            "thinking",
            "metadata",
            "confidence_score",
            "reasoning_steps",
            "session_id",
        ):
            assert key in result, f"missing key {key!r}"

    @pytest.mark.asyncio
    async def test_chat_error_path_keeps_the_same_keys(self, agent):
        with (
            patch("ai_devops_assistant.agents.agent.get_llm_service") as mock_llm,
            patch("ai_devops_assistant.agents.agent.get_tool_executor") as mock_exec,
            patch("ai_devops_assistant.agents.agent.get_session_manager") as mock_sm,
        ):
            mock_llm.return_value = _mock_agent_deps(chat_side_effect=Exception("nope"))
            mock_exec.return_value = MagicMock()
            mock_sm.return_value = MagicMock()
            await agent.initialize()

            result = await agent.chat("Hello", session_id="s1")

        assert result["success"] is False
        assert result["error"] == "nope"
        assert result["tool_calls"] == []
        assert result["session_id"] == "s1"


class TestRealTokenStreaming:
    """Phase 5.4: tokens come from the provider, not from chunking a finished string."""

    @pytest.fixture
    def agent(self):
        return DevOpsAgent()

    @staticmethod
    def _streaming_llm(chunks, stream_fails=None, chat_reply="fallback reply"):
        llm = AsyncMock()
        llm.health_check.return_value = True
        llm.chat.return_value = chat_reply

        async def _stream(messages, **kwargs):
            if stream_fails:
                raise stream_fails
            for chunk in chunks:
                yield chunk

        llm.stream_chat = _stream
        return llm

    @pytest.mark.asyncio
    async def test_tokens_come_from_the_provider_stream(self, agent):
        with (
            patch("ai_devops_assistant.agents.agent.get_llm_service") as mock_llm,
            patch("ai_devops_assistant.agents.agent.get_tool_executor") as mock_exec,
            patch("ai_devops_assistant.agents.agent.get_session_manager") as mock_sm,
        ):
            mock_llm.return_value = self._streaming_llm(["Three ", "pods ", "failed"])
            mock_exec.return_value = MagicMock()
            mock_sm.return_value = MagicMock()
            await agent.initialize()

            events = [e async for e in agent.chat_stream("q", session_id="s1")]

        tokens = [e.data["t"] for e in events if e.type is EventType.TOKEN]
        assert tokens == ["Three ", "pods ", "failed"], "chunk boundaries must be the provider's"

    @pytest.mark.asyncio
    async def test_the_done_message_is_the_joined_stream(self, agent):
        with (
            patch("ai_devops_assistant.agents.agent.get_llm_service") as mock_llm,
            patch("ai_devops_assistant.agents.agent.get_tool_executor") as mock_exec,
            patch("ai_devops_assistant.agents.agent.get_session_manager") as mock_sm,
        ):
            mock_llm.return_value = self._streaming_llm(["a", "b", "c"])
            mock_exec.return_value = MagicMock()
            mock_sm.return_value = MagicMock()
            await agent.initialize()

            events = [e async for e in agent.chat_stream("q", session_id="s1")]

        assert events[-1].data["message"] == "abc"

    @pytest.mark.asyncio
    async def test_a_broken_stream_falls_back_to_a_single_call(self, agent):
        """A provider with a broken streaming endpoint must not lose the reply."""
        with (
            patch("ai_devops_assistant.agents.agent.get_llm_service") as mock_llm,
            patch("ai_devops_assistant.agents.agent.get_tool_executor") as mock_exec,
            patch("ai_devops_assistant.agents.agent.get_session_manager") as mock_sm,
        ):
            mock_llm.return_value = self._streaming_llm(
                [], stream_fails=RuntimeError("streaming unsupported"), chat_reply="non-streamed"
            )
            mock_exec.return_value = MagicMock()
            mock_sm.return_value = MagicMock()
            await agent.initialize()

            events = [e async for e in agent.chat_stream("q", session_id="s1")]

        assert events[-1].type is EventType.DONE
        assert events[-1].data["message"] == "non-streamed"

    @pytest.mark.asyncio
    async def test_a_failure_after_the_first_token_is_not_retried(self, agent):
        """The caller has already rendered part of the answer; a retry would splice two."""
        llm = AsyncMock()
        llm.health_check.return_value = True
        llm.chat.return_value = "should not be used"

        async def _stream(messages, **kwargs):
            yield "partial "
            raise RuntimeError("connection lost")

        llm.stream_chat = _stream

        with (
            patch("ai_devops_assistant.agents.agent.get_llm_service", return_value=llm),
            patch("ai_devops_assistant.agents.agent.get_tool_executor") as mock_exec,
            patch("ai_devops_assistant.agents.agent.get_session_manager") as mock_sm,
        ):
            mock_exec.return_value = MagicMock()
            mock_sm.return_value = MagicMock()
            await agent.initialize()

            events = [e async for e in agent.chat_stream("q", session_id="s1")]

        assert events[-1].type is EventType.ERROR
        tokens = [e.data["t"] for e in events if e.type is EventType.TOKEN]
        assert tokens == ["partial "]

    @pytest.mark.asyncio
    async def test_the_provider_receives_a_system_and_a_user_message(self, agent):
        """The boundary must survive all the way to the provider call."""
        seen = {}

        llm = AsyncMock()
        llm.health_check.return_value = True

        async def _stream(messages, **kwargs):
            seen["messages"] = messages
            yield "ok"

        llm.stream_chat = _stream

        with (
            patch("ai_devops_assistant.agents.agent.get_llm_service", return_value=llm),
            patch("ai_devops_assistant.agents.agent.get_tool_executor") as mock_exec,
            patch("ai_devops_assistant.agents.agent.get_session_manager") as mock_sm,
        ):
            mock_exec.return_value = MagicMock()
            mock_sm.return_value = MagicMock()
            await agent.initialize()

            [e async for e in agent.chat_stream("q", session_id="s1")]

        assert [m["role"] for m in seen["messages"]] == ["system", "user"]
