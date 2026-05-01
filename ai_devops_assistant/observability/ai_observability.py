"""AI observability primitives for request and LLM tracing."""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# Context variables for distributed tracing
_request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
_trace_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
_span_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("span_id", default="")


def generate_request_id() -> str:
    """Generate a unique request id."""
    return str(uuid.uuid4())


def generate_trace_id() -> str:
    """Generate a unique trace id."""
    return str(uuid.uuid4())


def generate_span_id() -> str:
    """Generate a unique span id."""
    return str(uuid.uuid4())


def set_request_id(request_id: str) -> None:
    """Store request id in context."""
    _request_id_ctx.set(request_id)


def get_request_id() -> str:
    """Get request id from context."""
    return _request_id_ctx.get("")


def set_trace_id(trace_id: str) -> None:
    """Store trace id in context."""
    _trace_id_ctx.set(trace_id)


def get_trace_id() -> str:
    """Get trace id from context."""
    return _trace_id_ctx.get("")


def set_span_id(span_id: str) -> None:
    """Store span id in context."""
    _span_id_ctx.set(span_id)


def get_span_id() -> str:
    """Get span id from context."""
    return _span_id_ctx.get("")


@dataclass
class TraceSpan:
    """Represents a single operation span in a distributed trace."""

    name: str
    service: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    trace_id: str = field(default_factory=get_trace_id)
    span_id: str = field(default_factory=generate_span_id)
    parent_span_id: Optional[str] = None
    tags: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        """Add an event to the span."""
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {},
        })

    def set_tag(self, key: str, value: Any) -> None:
        """Set a tag on the span."""
        self.tags[key] = value

    def finish(self, error: Optional[str] = None) -> None:
        """Finish the span."""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.error = error


@dataclass
class LLMTrace:
    """Captures a single LLM request/response lifecycle for logging."""

    provider: str
    model: str
    prompt: str
    request_id: str = field(default_factory=get_request_id)
    trace_id: str = field(default_factory=get_trace_id)
    span_id: str = field(default_factory=generate_span_id)
    started_at: float = field(default_factory=time.perf_counter)
    metadata: Dict[str, Any] = field(default_factory=dict)
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    response: Optional[str] = None
    error: Optional[str] = None
    latency_ms: Optional[float] = None

    def complete(
        self,
        response: Optional[str] = None,
        error: Optional[str] = None,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
    ) -> None:
        """Emit structured completion log."""
        self.latency_ms = round((time.perf_counter() - self.started_at) * 1000, 2)
        self.response = response
        self.error = error
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens or (prompt_tokens or 0) + (completion_tokens or 0)

        # Log structured event
        log_data = {
            "event": "llm_request",
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "provider": self.provider,
            "model": self.model,
            "prompt_length": len(self.prompt or ""),
            "response_length": len(response or "") if response else 0,
            "latency_ms": self.latency_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "error": self.error,
            "metadata": self.metadata,
        }

        if error:
            logger.error("LLM request failed", extra=log_data)
        else:
            logger.info("LLM request completed", extra=log_data)


class MetricsCollector:
    """Collects and aggregates AI observability metrics."""

    def __init__(self, max_history: int = 10000):
        self.max_history = max_history
        self._lock = threading.Lock()

        # Metrics storage
        self.llm_requests = deque(maxlen=max_history)
        self.errors = deque(maxlen=max_history)
        self.latencies = defaultdict(lambda: deque(maxlen=max_history))
        self.token_usage = defaultdict(lambda: deque(maxlen=max_history))

        # Aggregated metrics
        self.total_requests = 0
        self.total_errors = 0
        self.total_tokens = 0

    def record_llm_request(self, trace: LLMTrace) -> None:
        """Record an LLM request for metrics collection."""
        with self._lock:
            self.llm_requests.append({
                "timestamp": time.time(),
                "provider": trace.provider,
                "model": trace.model,
                "latency_ms": trace.latency_ms,
                "prompt_tokens": trace.prompt_tokens,
                "completion_tokens": trace.completion_tokens,
                "total_tokens": trace.total_tokens,
                "error": trace.error is not None,
            })

            self.total_requests += 1
            if trace.error:
                self.total_errors += 1
                self.errors.append({
                    "timestamp": time.time(),
                    "provider": trace.provider,
                    "model": trace.model,
                    "error": trace.error,
                })

            if trace.total_tokens:
                self.total_tokens += trace.total_tokens

            # Record latency by model
            if trace.latency_ms is not None:
                self.latencies[trace.model].append(trace.latency_ms)

            # Record token usage by model
            if trace.total_tokens:
                self.token_usage[trace.model].append(trace.total_tokens)

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get current metrics summary."""
        with self._lock:
            current_time = time.time()
            last_hour = current_time - 3600

            # Calculate recent metrics
            recent_requests = [r for r in self.llm_requests if r["timestamp"] > last_hour]
            recent_errors = [r for r in self.errors if r["timestamp"] > last_hour]

            # Calculate averages
            avg_latencies = {}
            for model, latencies in self.latencies.items():
                if latencies:
                    avg_latencies[model] = sum(latencies) / len(latencies)

            avg_token_usage = {}
            for model, tokens in self.token_usage.items():
                if tokens:
                    avg_token_usage[model] = sum(tokens) / len(tokens)

            return {
                "total_requests": self.total_requests,
                "total_errors": self.total_errors,
                "total_tokens": self.total_tokens,
                "error_rate": self.total_errors / max(self.total_requests, 1),
                "recent_requests_last_hour": len(recent_requests),
                "recent_errors_last_hour": len(recent_errors),
                "recent_error_rate": len(recent_errors) / max(len(recent_requests), 1),
                "average_latencies_by_model": avg_latencies,
                "average_tokens_by_model": avg_token_usage,
                "models_used": list(self.latencies.keys()),
            }

    def get_prometheus_metrics(self) -> str:
        """Generate Prometheus-compatible metrics output."""
        metrics = self.get_metrics_summary()

        lines = [
            "# HELP ai_llm_requests_total Total number of LLM requests",
            "# TYPE ai_llm_requests_total counter",
            f"ai_llm_requests_total {metrics['total_requests']}",
            "",
            "# HELP ai_llm_errors_total Total number of LLM errors",
            "# TYPE ai_llm_errors_total counter",
            f"ai_llm_errors_total {metrics['total_errors']}",
            "",
            "# HELP ai_llm_tokens_total Total number of tokens used",
            "# TYPE ai_llm_tokens_total counter",
            f"ai_llm_tokens_total {metrics['total_tokens']}",
            "",
            "# HELP ai_llm_error_rate Error rate (0.0-1.0)",
            "# TYPE ai_llm_error_rate gauge",
            f"ai_llm_error_rate {metrics['error_rate']}",
            "",
        ]

        # Per-model metrics
        for model, avg_latency in metrics["average_latencies_by_model"].items():
            lines.extend([
                f"# HELP ai_llm_latency_ms_avg Average latency in milliseconds for {model}",
                f"# TYPE ai_llm_latency_ms_avg gauge",
                f'ai_llm_latency_ms_avg{{model="{model}"}} {avg_latency}',
                "",
            ])

        for model, avg_tokens in metrics["average_tokens_by_model"].items():
            lines.extend([
                f"# HELP ai_llm_tokens_avg Average tokens per request for {model}",
                f"# TYPE ai_llm_tokens_avg gauge",
                f'ai_llm_tokens_avg{{model="{model}"}} {avg_tokens}',
                "",
            ])

        return "\n".join(lines)


class ObservabilityManager:
    """Central manager for AI observability features."""

    def __init__(self):
        self.metrics_collector = MetricsCollector()
        self.active_traces: Dict[str, TraceSpan] = {}
        self._lock = threading.Lock()

    def start_trace(
        self,
        name: str,
        service: str = "ai-devops-assistant",
        parent_span_id: Optional[str] = None,
        tags: Optional[Dict[str, Any]] = None,
    ) -> TraceSpan:
        """Start a new trace span."""
        span = TraceSpan(
            name=name,
            service=service,
            parent_span_id=parent_span_id or get_span_id(),
            tags=tags or {},
        )

        with self._lock:
            self.active_traces[span.span_id] = span

        # Set span context
        set_span_id(span.span_id)

        return span

    def finish_trace(self, span: TraceSpan, error: Optional[str] = None) -> None:
        """Finish a trace span."""
        span.finish(error)

        with self._lock:
            if span.span_id in self.active_traces:
                del self.active_traces[span.span_id]

        # Log span completion
        log_data = {
            "event": "trace_span",
            "trace_id": span.trace_id,
            "span_id": span.span_id,
            "parent_span_id": span.parent_span_id,
            "trace_name": span.name,
            "service": span.service,
            "duration_ms": span.duration_ms,
            "error": span.error,
            "tags": span.tags,
            "events": span.events,
        }

        if error:
            logger.error("Trace span completed with error", extra=log_data)
        else:
            logger.info("Trace span completed", extra=log_data)

    async def trace_llm_call(
        self,
        provider: str,
        model: str,
        prompt: str,
        call_fn: callable,
        **kwargs
    ) -> str:
        """Trace an LLM call with automatic metrics collection."""
        # Start trace span
        span = self.start_trace(
            name=f"llm_call_{provider}_{model}",
            service="llm_service",
            tags={"provider": provider, "model": model, "operation": "generate"}
        )

        # Create LLM trace
        trace = LLMTrace(
            provider=provider,
            model=model,
            prompt=prompt,
            temperature=kwargs.get("temperature"),
            max_tokens=kwargs.get("max_tokens"),
        )

        span.add_event("llm_request_started", {
            "prompt_length": len(prompt),
            "temperature": kwargs.get("temperature"),
            "max_tokens": kwargs.get("max_tokens"),
        })

        try:
            # Make the call
            response = await call_fn()

            # Complete trace
            trace.complete(
                response=response,
                prompt_tokens=getattr(response, 'prompt_tokens', None),
                completion_tokens=getattr(response, 'completion_tokens', None),
                total_tokens=getattr(response, 'total_tokens', None),
            )

            span.add_event("llm_request_completed", {
                "response_length": len(response) if isinstance(response, str) else 0,
                "tokens_used": trace.total_tokens,
            })

            self.finish_trace(span)
            self.metrics_collector.record_llm_request(trace)

            return response if isinstance(response, str) else str(response)

        except Exception as e:
            error_msg = str(e)
            trace.complete(error=error_msg)
            span.add_event("llm_request_failed", {"error": error_msg})

            self.finish_trace(span, error_msg)
            self.metrics_collector.record_llm_request(trace)

            raise

    def get_metrics_endpoint(self) -> str:
        """Get Prometheus metrics for HTTP endpoint."""
        return self.metrics_collector.get_prometheus_metrics()

    def get_health_status(self) -> Dict[str, Any]:
        """Get system health status."""
        metrics = self.metrics_collector.get_metrics_summary()

        # Determine health based on error rates
        error_rate = metrics["error_rate"]
        recent_error_rate = metrics["recent_error_rate"]

        if recent_error_rate > 0.1:  # 10% error rate
            health = "unhealthy"
        elif error_rate > 0.05:  # 5% error rate
            health = "degraded"
        else:
            health = "healthy"

        return {
            "status": health,
            "timestamp": time.time(),
            "metrics": metrics,
            "active_traces": len(self.active_traces),
        }


# Global observability manager instance
observability_manager = ObservabilityManager()


# Convenience functions
def start_request_trace(request_id: Optional[str] = None) -> str:
    """Start tracing for a new request."""
    req_id = request_id or generate_request_id()
    trace_id = generate_trace_id()

    set_request_id(req_id)
    set_trace_id(trace_id)

    # Start root span
    span = observability_manager.start_trace(
        name="http_request",
        service="ai-devops-assistant",
        tags={"request_id": req_id}
    )

    return req_id


def finish_request_trace(error: Optional[str] = None) -> None:
    """Finish tracing for the current request."""
    # Find and finish the root span
    current_span_id = get_span_id()
    if current_span_id:
        with observability_manager._lock:
            if current_span_id in observability_manager.active_traces:
                span = observability_manager.active_traces[current_span_id]
                observability_manager.finish_trace(span, error)


# Context manager for automatic trace management
class trace_context:
    """Context manager for automatic span tracing."""

    def __init__(self, name: str, service: str = "ai-devops-assistant", **tags):
        self.name = name
        self.service = service
        self.tags = tags
        self.span: Optional[TraceSpan] = None

    def __enter__(self) -> TraceSpan:
        self.span = observability_manager.start_trace(
            name=self.name,
            service=self.service,
            tags=self.tags
        )
        return self.span

    def __exit__(self, exc_type, exc_val, exc_tb):
        error = str(exc_val) if exc_val else None
        if self.span:
            observability_manager.finish_trace(self.span, error)

        payload = {
            "trace_name": self.name,
            "service": self.service,
            "error": error,
            **self.tags,
        }

        if error:
            logger.error("trace_context failed", extra=payload)
        else:
            logger.info("trace_context completed", extra=payload)
