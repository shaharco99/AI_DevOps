"""AI observability primitives for request and LLM tracing."""

from __future__ import annotations

import contextvars
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

_request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


def generate_request_id() -> str:
    """Generate a unique request id."""
    return str(uuid.uuid4())


def set_request_id(request_id: str) -> None:
    """Store request id in context."""
    _request_id_ctx.set(request_id)


def get_request_id() -> str:
    """Get request id from context."""
    return _request_id_ctx.get("")


@dataclass
class LLMTrace:
    """Captures a single LLM request/response lifecycle for logging."""

    provider: str
    model: str
    prompt: str
    request_id: str = field(default_factory=get_request_id)
    started_at: float = field(default_factory=time.perf_counter)
    metadata: dict[str, Any] = field(default_factory=dict)

    def complete(self, response: str, error: Optional[str] = None) -> None:
        """Emit structured completion log."""
        elapsed_ms = round((time.perf_counter() - self.started_at) * 1000, 2)
        prompt_chars = len(self.prompt or "")
        response_chars = len(response or "")
        payload = {
            "event": "llm_trace",
            "request_id": self.request_id,
            "provider": self.provider,
            "model": self.model,
            "latency_ms": elapsed_ms,
            "prompt_chars": prompt_chars,
            "response_chars": response_chars,
            "error": error,
            **self.metadata,
        }
        if error:
            logger.error("llm_call_failed", extra=payload)
        else:
            logger.info("llm_call_completed", extra=payload)
