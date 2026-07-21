"""Events emitted by the agent while it works.

`DevOpsAgent.chat_stream()` yields these so a caller can observe progress as it
happens instead of waiting for a finished response. `DevOpsAgent.chat()` consumes
the same stream and folds it back into a single dict, so there is exactly one
implementation of the agent loop.

Event payloads are JSON-safe by construction: the SSE endpoint serialises them
directly, and `AgentEvent.to_sse_dict()` is the single place that shape is
defined.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    """Types of event the agent can emit.

    str-valued so the member serialises as its wire name without conversion.
    """

    STATUS = "status"  # phase changed (planning, executing, responding)
    RAG = "rag"  # retrieved context; titles and scores, never full documents
    PLAN = "plan"  # the execution plan, so a UI can show upcoming steps
    TOOL_START = "tool_start"  # a tool call began
    TOOL_END = "tool_end"  # a tool call finished (ok/error + duration)
    TOKEN = "token"  # an incremental piece of the final response
    DONE = "done"  # terminal success; carries the complete response
    ERROR = "error"  # terminal failure


# Events after which no further events are emitted.
TERMINAL_EVENTS = frozenset({EventType.DONE, EventType.ERROR})


@dataclass
class AgentEvent:
    """A single event in an agent run."""

    type: EventType
    data: dict[str, Any] = field(default_factory=dict)

    def to_sse_dict(self) -> dict[str, Any]:
        """Render as the {event, data} pair the SSE layer sends.

        Kept here rather than in the route so the wire format has one definition
        that both the endpoint and its tests refer to.
        """
        return {"event": self.type.value, "data": self.data}

    @property
    def is_terminal(self) -> bool:
        """Whether this event ends the stream."""
        return self.type in TERMINAL_EVENTS


def status_event(phase: str) -> AgentEvent:
    """Build a status event for a named phase."""
    return AgentEvent(type=EventType.STATUS, data={"phase": phase})


def error_event(message: str, recoverable: bool = False) -> AgentEvent:
    """Build a terminal error event."""
    return AgentEvent(type=EventType.ERROR, data={"message": message, "recoverable": recoverable})
