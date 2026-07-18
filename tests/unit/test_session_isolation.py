"""Session isolation and storage.

The first class covers a real cross-user data leak: the process-wide agent held
conversation memory as instance state, so the second user to arrive inherited the
first user's history verbatim.
"""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_devops_assistant.agents.agent import AgentTask, DevOpsAgent, get_agent
from ai_devops_assistant.agents.memory import ConversationMemory, SessionManager
from ai_devops_assistant.agents.session_store import (
    InMemorySessionStore,
    RedisSessionStore,
    build_session_store,
    deserialize_memory,
    serialize_memory,
)
from ai_devops_assistant.config.settings import settings


class TestNoCrossSessionBleed:
    """The agent is a singleton; it must hold no per-user state."""

    def test_the_agent_holds_no_conversation_memory_attribute(self):
        """Instance state on a shared singleton is shared by every request."""
        agent = DevOpsAgent()
        assert not hasattr(
            agent, "conversation_memory"
        ), "conversation memory on the agent is shared across all users"

    @pytest.mark.asyncio
    async def test_one_users_history_does_not_reach_another(self):
        agent = DevOpsAgent()
        manager = agent.session_manager

        alice = manager.get_or_create_session("alice")
        alice.add_message("user", "MY SECRET IS ALICE-1234")

        bob_context = await agent._gather_context(
            AgentTask(description="what did the last user say?"),
            use_rag=False,
            memory=manager.get_or_create_session("bob"),
        )

        assert "ALICE-1234" not in bob_context

    @pytest.mark.asyncio
    async def test_a_user_still_sees_their_own_history(self):
        agent = DevOpsAgent()
        memory = agent.session_manager.get_or_create_session("alice")
        memory.add_message("user", "my cluster is called prod-eu")

        context = await agent._gather_context(
            AgentTask(description="which cluster?"), use_rag=False, memory=memory
        )
        assert "prod-eu" in context

    @pytest.mark.asyncio
    async def test_no_memory_means_no_history_section(self):
        agent = DevOpsAgent()
        context = await agent._gather_context(
            AgentTask(description="q"), use_rag=False, memory=None
        )
        assert "Recent conversation" not in context

    @pytest.mark.asyncio
    async def test_two_sequential_chats_do_not_share_memory(self):
        """End to end through the singleton, which is how the leak happened."""
        import ai_devops_assistant.agents.agent as agent_module

        agent_module._agent = None
        llm = AsyncMock()
        llm.health_check.return_value = True

        async def _stream(messages, **kwargs):
            yield "reply"

        llm.stream_chat = _stream

        with (
            patch("ai_devops_assistant.agents.agent.get_llm_service", return_value=llm),
            patch("ai_devops_assistant.agents.agent.get_tool_executor", return_value=MagicMock()),
            patch.object(
                DevOpsAgent,
                "_create_execution_plan",
                new=AsyncMock(return_value=[{"action": "direct_response"}]),
            ),
        ):
            agent = await get_agent()
            await agent.chat("SECRET-ALPHA", session_id="user-one")

            second = await get_agent()
            context = await second._gather_context(
                AgentTask(description="recall"),
                use_rag=False,
                memory=second.session_manager.get_or_create_session("user-two"),
            )

        agent_module._agent = None
        assert "SECRET-ALPHA" not in context


class TestRequestScopedDatabaseSession:
    """The tool registry is shared; the session must not be."""

    def test_a_tool_prefers_the_context_session(self):
        from ai_devops_assistant.database.context import reset_current_session, set_current_session
        from ai_devops_assistant.tools.sql_tool import SQLQueryTool

        tool = SQLQueryTool()
        explicit = MagicMock(name="explicitly-set-session")
        contextual = MagicMock(name="request-scoped-session")

        tool.set_session(explicit)
        assert tool.session is explicit

        token = set_current_session(contextual)
        try:
            assert tool.session is contextual, "request context must win"
        finally:
            reset_current_session(token)

        assert tool.session is explicit, "context reset restores the previous value"

    def test_no_context_and_no_explicit_session_is_none(self):
        from ai_devops_assistant.tools.sql_tool import SQLQueryTool

        assert SQLQueryTool().session is None

    def test_context_is_isolated_between_async_tasks(self):
        """asyncio copies the context per task, which is why this works."""
        import asyncio

        from ai_devops_assistant.database.context import get_current_session, set_current_session

        async def worker(name):
            set_current_session(name)
            await asyncio.sleep(0)
            return get_current_session()

        async def main():
            return await asyncio.gather(worker("session-a"), worker("session-b"))

        assert asyncio.run(main()) == ["session-a", "session-b"]


class TestMemorySerialization:
    def test_round_trip_preserves_messages(self):
        memory = ConversationMemory()
        memory.add_message("user", "hello")
        memory.add_message("assistant", "hi")

        restored = deserialize_memory(serialize_memory(memory))
        assert [m["content"] for m in restored.get_last_n_messages(5)] == ["hello", "hi"]

    def test_timestamps_do_not_break_serialization(self):
        """Messages carry datetime objects, which json cannot encode natively."""
        memory = ConversationMemory()
        memory.add_message("user", "hello")
        payload = serialize_memory(memory)
        assert json.loads(payload)["messages"][0]["timestamp"]

    def test_max_turns_is_preserved(self):
        memory = ConversationMemory(max_turns=3)
        restored = deserialize_memory(serialize_memory(memory))
        assert restored.messages.maxlen == 3

    def test_an_unreadable_payload_yields_an_empty_memory(self):
        """Losing one conversation beats 500ing every request that touches it."""
        restored = deserialize_memory("{not json")
        assert restored.get_last_n_messages(5) == []


class TestInMemorySessionStore:
    def test_save_and_get(self):
        store = InMemorySessionStore()
        memory = ConversationMemory()
        memory.add_message("user", "hi")
        store.save("s1", memory)
        assert store.get("s1") is memory

    def test_missing_session_is_none(self):
        assert InMemorySessionStore().get("nope") is None

    def test_delete_and_list(self):
        store = InMemorySessionStore()
        store.save("s1", ConversationMemory())
        assert store.list_sessions() == ["s1"]
        store.delete("s1")
        assert store.list_sessions() == []

    def test_deleting_an_absent_session_is_not_an_error(self):
        InMemorySessionStore().delete("nope")


class TestStoreSelection:
    def test_no_redis_url_gives_the_in_process_store(self):
        with patch.object(settings, "REDIS_URL", ""):
            assert isinstance(build_session_store(), InMemorySessionStore)

    def test_an_unreachable_redis_falls_back_rather_than_failing_startup(self):
        """Degraded conversational memory beats a deployment that will not boot."""
        with patch.object(settings, "REDIS_URL", "redis://127.0.0.1:1/0"):
            assert isinstance(build_session_store(), InMemorySessionStore)

    def test_session_manager_uses_the_injected_store(self):
        store = InMemorySessionStore()
        manager = SessionManager(store=store)
        manager.get_or_create_session("s1")
        assert store.list_sessions() == ["s1"]


REDIS_URL = os.environ.get("TEST_REDIS_URL")


@pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL not set")
class TestRedisSessionStore:
    """Against a real Redis.

    Run with:
        docker run -d --name redis-test -p 56379:6379 redis:7-alpine
        TEST_REDIS_URL=redis://127.0.0.1:56379/0 pytest tests/unit/test_session_isolation.py
    """

    @pytest.fixture
    def store(self):
        store = RedisSessionStore(REDIS_URL, ttl_seconds=60)
        yield store
        for session_id in store.list_sessions():
            store.delete(session_id)

    def test_save_and_get_round_trip(self, store):
        memory = ConversationMemory()
        memory.add_message("user", "my deployment is payments-api")
        store.save("s1", memory)

        recovered = store.get("s1")
        assert recovered is not None
        assert "payments-api" in recovered.get_last_n_messages(1)[0]["content"]

    def test_a_second_process_recovers_the_session(self, store):
        """The actual point: WEB_CONCURRENCY>1 and restarts must not lose history."""
        memory = ConversationMemory()
        memory.add_message("user", "remember this")
        store.save("shared", memory)

        other_worker = RedisSessionStore(REDIS_URL, ttl_seconds=60)
        recovered = other_worker.get("shared")
        assert recovered is not None
        assert recovered.get_last_n_messages(1)[0]["content"] == "remember this"

    def test_missing_session_is_none(self, store):
        assert store.get("never-created") is None

    def test_delete_removes_it(self, store):
        store.save("gone", ConversationMemory())
        store.delete("gone")
        assert store.get("gone") is None

    def test_list_sessions_strips_the_key_prefix(self, store):
        store.save("plain-id", ConversationMemory())
        assert "plain-id" in store.list_sessions()

    def test_a_ttl_is_set_on_save(self, store):
        """Expiry tracks last use, so there is no sweeper to run."""
        store.save("expiring", ConversationMemory())
        assert store._redis.ttl(store._key("expiring")) > 0
