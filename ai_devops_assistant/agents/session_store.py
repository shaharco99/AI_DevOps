"""Where conversation memory lives between requests.

SessionManager kept memories in a process dictionary. That is wrong in two ways
the deployment already exercises:

- the Dockerfile runs uvicorn with WEB_CONCURRENCY workers, and a user's turns
  land on whichever worker the load balancer picks, so the conversation appears
  to lose its memory at random;
- a restart or a rolling deploy drops every in-flight conversation.

Redis was already provisioned in docker-compose with a healthcheck and a volume,
and connected to by nothing at all. It is the natural home for this.

The store is chosen at runtime: Redis when REDIS_URL is set, otherwise the
in-process dictionary, which keeps tests and single-process development working
with no server to run. Durable chat history is separate — it lives in Postgres
via database/queries.py — so a Redis outage costs conversational context, not the
transcript.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from ai_devops_assistant.agents.memory import ConversationMemory
from ai_devops_assistant.config.settings import settings

logger = logging.getLogger(__name__)


class SessionStore(Protocol):
    """Storage for per-session conversation memory."""

    def get(self, session_id: str) -> ConversationMemory | None:
        """Return the memory for a session, or None."""
        ...

    def save(self, session_id: str, memory: ConversationMemory) -> None:
        """Persist a session's memory."""
        ...

    def delete(self, session_id: str) -> None:
        """Remove a session."""
        ...

    def list_sessions(self) -> list[str]:
        """Known session ids."""
        ...


def serialize_memory(memory: ConversationMemory) -> str:
    """Render a memory as JSON for storage."""
    # default=str because messages carry datetime timestamps, which json cannot
    # encode. They are only ever displayed, so the ISO string is sufficient.
    return json.dumps(
        {
            "messages": list(memory.messages),
            "context": getattr(memory, "context", {}),
            "max_turns": memory.messages.maxlen,
        },
        default=str,
    )


def deserialize_memory(payload: str) -> ConversationMemory:
    """Rebuild a memory from stored JSON.

    A malformed payload yields an empty memory rather than raising: losing the
    context of one conversation is a far better failure than a 500 on every
    request that touches it.
    """
    memory = ConversationMemory()
    try:
        data: dict[str, Any] = json.loads(payload)
    except (TypeError, ValueError) as e:
        logger.warning(f"Discarding unreadable session payload: {e}")
        return memory

    if data.get("max_turns"):
        memory = ConversationMemory(max_turns=int(data["max_turns"]))
    for message in data.get("messages", []):
        memory.messages.append(message)
    if isinstance(data.get("context"), dict):
        memory.context = data["context"]
    return memory


class InMemorySessionStore:
    """Process-local store. Used by tests and single-process development."""

    def __init__(self) -> None:
        self._sessions: dict[str, ConversationMemory] = {}

    def get(self, session_id: str) -> ConversationMemory | None:
        return self._sessions.get(session_id)

    def save(self, session_id: str, memory: ConversationMemory) -> None:
        self._sessions[session_id] = memory

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def list_sessions(self) -> list[str]:
        return list(self._sessions)


class RedisSessionStore:
    """Redis-backed store, shared by every worker and surviving restarts."""

    KEY_PREFIX = "session:"

    def __init__(self, url: str, ttl_seconds: int = 3600):
        import redis

        self._redis = redis.Redis.from_url(url, decode_responses=True)
        self._ttl = ttl_seconds

    def _key(self, session_id: str) -> str:
        return f"{self.KEY_PREFIX}{session_id}"

    def get(self, session_id: str) -> ConversationMemory | None:
        try:
            payload = self._redis.get(self._key(session_id))
        except Exception as e:
            # Degrade to "no history" rather than failing the request: a Redis
            # outage should cost conversational context, not availability.
            logger.warning(f"Redis read failed for {session_id}: {e}")
            return None
        return deserialize_memory(payload) if payload else None

    def save(self, session_id: str, memory: ConversationMemory) -> None:
        try:
            # Written with a TTL on every save, so the expiry tracks last use
            # rather than creation and there is no sweeper to run.
            self._redis.setex(self._key(session_id), self._ttl, serialize_memory(memory))
        except Exception as e:
            logger.warning(f"Redis write failed for {session_id}: {e}")

    def delete(self, session_id: str) -> None:
        try:
            self._redis.delete(self._key(session_id))
        except Exception as e:
            logger.warning(f"Redis delete failed for {session_id}: {e}")

    def list_sessions(self) -> list[str]:
        try:
            # scan_iter, not keys(): KEYS blocks the server for the whole scan.
            return [
                key.removeprefix(self.KEY_PREFIX)
                for key in self._redis.scan_iter(match=f"{self.KEY_PREFIX}*")
            ]
        except Exception as e:
            logger.warning(f"Redis scan failed: {e}")
            return []


def build_session_store() -> SessionStore:
    """Build the configured store, falling back to the in-process one."""
    if not settings.REDIS_URL:
        logger.info("REDIS_URL not set; using in-process session storage")
        return InMemorySessionStore()

    try:
        store = RedisSessionStore(
            settings.REDIS_URL, ttl_seconds=settings.SESSION_STORE_TTL_SECONDS
        )
        store._redis.ping()
        logger.info("Using Redis-backed session storage")
        return store
    except Exception as e:
        # Starting without conversational memory beats not starting at all; the
        # log line is what tells an operator the deployment is degraded.
        logger.error(f"Redis unavailable ({e}); falling back to in-process sessions")
        return InMemorySessionStore()
