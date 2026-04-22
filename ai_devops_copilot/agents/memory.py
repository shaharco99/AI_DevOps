"""Conversation memory management for multi-turn conversations."""

import logging
from collections import deque
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class ConversationMemory:
    """Manage conversation history for multi-turn interactions."""

    def __init__(self, max_turns: int = 20):
        """Initialize conversation memory.
        
        Args:
            max_turns: Maximum number of turns to keep in memory
        """
        self.max_turns = max_turns
        self.messages: deque = deque(maxlen=max_turns)
        self.started_at = datetime.utcnow()
        self.context: dict = {}

    def add_message(self, role: str, content: str, metadata: Optional[dict] = None) -> None:
        """Add message to memory.
        
        Args:
            role: Message role (user, assistant, system)
            content: Message content
            metadata: Optional metadata
        """
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow(),
            "metadata": metadata or {},
        }
        self.messages.append(message)
        logger.debug(f"Added message: {role}")

    def get_messages(self) -> list[dict]:
        """Get all messages in conversation."""
        return list(self.messages)

    def get_last_n_messages(self, n: int) -> list[dict]:
        """Get last n messages."""
        return list(self.messages)[-n:]

    def get_context(self, key: str) -> Optional[str]:
        """Get context value."""
        return self.context.get(key)

    def set_context(self, key: str, value: str) -> None:
        """Set context value."""
        self.context[key] = value

    def get_formatted_history(self) -> str:
        """Get formatted message history for LLM context."""
        history_parts = []
        for msg in self.messages:
            role = msg["role"]
            content = msg["content"][:500]  # Truncate long messages
            history_parts.append(f"{role}: {content}")
        return "\n".join(history_parts)

    def clear(self) -> None:
        """Clear conversation memory."""
        self.messages.clear()
        self.context.clear()
        logger.debug("Conversation memory cleared")

    def get_summary(self) -> dict:
        """Get conversation summary."""
        return {
            "message_count": len(self.messages),
            "started_at": self.started_at,
            "duration_seconds": (datetime.utcnow() - self.started_at).total_seconds(),
            "context_keys": list(self.context.keys()),
        }


class SessionManager:
    """Manage multiple conversation sessions."""

    def __init__(self, session_ttl_minutes: int = 60):
        """Initialize session manager.
        
        Args:
            session_ttl_minutes: Session time-to-live in minutes
        """
        self.session_ttl_minutes = session_ttl_minutes
        self.sessions: dict[str, ConversationMemory] = {}

    def create_session(self, session_id: str) -> ConversationMemory:
        """Create new session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            ConversationMemory: New session memory
        """
        if session_id in self.sessions:
            logger.warning(f"Session {session_id} already exists")
            return self.sessions[session_id]

        session = ConversationMemory()
        self.sessions[session_id] = session
        logger.info(f"Created session: {session_id}")
        return session

    def get_session(self, session_id: str) -> Optional[ConversationMemory]:
        """Get existing session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            ConversationMemory or None
        """
        return self.sessions.get(session_id)

    def delete_session(self, session_id: str) -> None:
        """Delete session.
        
        Args:
            session_id: Session identifier
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Deleted session: {session_id}")

    def list_sessions(self) -> list[str]:
        """List all session IDs."""
        return list(self.sessions.keys())

    def get_or_create_session(self, session_id: str) -> ConversationMemory:
        """Get existing session or create new one."""
        session = self.get_session(session_id)
        if session is None:
            session = self.create_session(session_id)
        return session


# Global instance
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Get or create session manager."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
