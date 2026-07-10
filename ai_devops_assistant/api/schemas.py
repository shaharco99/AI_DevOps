"""API request and response schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ============================================================================
# Health Check Schemas
# ============================================================================


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Health status")
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Environment (development/production)")
    timestamp: datetime = Field(..., description="Response timestamp")


# ============================================================================
# Chat Schemas
# ============================================================================


class ChatRequest(BaseModel):
    """Chat request."""

    message: str = Field(..., description="User message")
    session_id: str | None = Field(None, description="Optional session ID for context")
    include_tools: list[str] | None = Field(
        None,
        description="Optional list of tools to limit agent to specific tools",
    )


class ToolCall(BaseModel):
    """Tool call information."""

    tool_name: str = Field(..., description="Name of the tool")
    parameters: dict[str, Any] = Field(..., description="Tool parameters")
    result: Any | None = Field(None, description="Tool execution result")


class ChatResponse(BaseModel):
    """Chat response."""

    session_id: str = Field(..., description="Session ID")
    message: str = Field(..., description="Assistant response")
    tool_calls: list[ToolCall] | None = Field(
        None,
        description="Tools called to generate response",
    )
    thinking: str | None = Field(
        None,
        description="Agent's reasoning process (if available)",
    )


# ============================================================================
# SQL Schemas
# ============================================================================


class SQLQueryRequest(BaseModel):
    """SQL query request."""

    query: str = Field(..., description="SQL query to execute")
    limit: int | None = Field(1000, description="Maximum rows to return")


class SQLQueryResponse(BaseModel):
    """SQL query response."""

    rows: list[dict[str, Any]] = Field(..., description="Query results")
    count: int = Field(..., description="Number of rows returned")
    execution_time_ms: float = Field(..., description="Query execution time in milliseconds")


# ============================================================================
# Log Analysis Schemas
# ============================================================================


class LogAnalysisRequest(BaseModel):
    """Log analysis request."""

    query: str = Field(..., description="Search query for logs")
    limit: int | None = Field(100, description="Maximum logs to return")
    time_range_hours: int | None = Field(1, description="Time range in hours")


class LogEntry(BaseModel):
    """Single log entry."""

    timestamp: datetime = Field(..., description="Log timestamp")
    level: str = Field(..., description="Log level (INFO, ERROR, WARNING, etc.)")
    message: str = Field(..., description="Log message")
    source: str = Field(..., description="Source of log")
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata")


class LogAnalysisResponse(BaseModel):
    """Log analysis response."""

    logs: list[LogEntry] = Field(..., description="Matched log entries")
    count: int = Field(..., description="Total logs returned")
    analysis: str | None = Field(None, description="AI analysis of logs")


# ============================================================================
# Metrics Schemas
# ============================================================================


class MetricsQueryRequest(BaseModel):
    """Metrics query request."""

    query: str = Field(..., description="Prometheus query string")
    duration: str | None = Field("1h", description="Query duration")


class MetricPoint(BaseModel):
    """Single metric data point."""

    timestamp: int = Field(..., description="Unix timestamp")
    value: float = Field(..., description="Metric value")


class TimeSeries(BaseModel):
    """Time series data."""

    metric_name: str = Field(..., description="Metric name")
    labels: dict[str, str] = Field(..., description="Metric labels")
    values: list[MetricPoint] = Field(..., description="Data points")


class MetricsQueryResponse(BaseModel):
    """Metrics query response."""

    time_series: list[TimeSeries] = Field(..., description="Returned time series")
    query_time_ms: float = Field(..., description="Query time in milliseconds")


# ============================================================================
# Pipeline Status Schemas
# ============================================================================


class PipelineRun(BaseModel):
    """Pipeline run information."""

    run_id: str = Field(..., description="Run ID")
    status: str = Field(..., description="Run status")
    branch: str = Field(..., description="Branch name")
    commit: str = Field(..., description="Commit hash")
    started_at: datetime = Field(..., description="Start time")
    ended_at: datetime | None = Field(None, description="End time")
    duration_seconds: int | None = Field(None, description="Duration in seconds")


class PipelineStatusResponse(BaseModel):
    """Pipeline status response."""

    runs: list[PipelineRun] = Field(..., description="Recent pipeline runs")
    total_count: int = Field(..., description="Total runs")


# ============================================================================
# Error Schemas
# ============================================================================


class ErrorDetail(BaseModel):
    """Error detail."""

    error: str = Field(..., description="Error message")
    code: str | None = Field(None, description="Error code")
    details: dict[str, Any] | None = Field(None, description="Additional details")
    timestamp: datetime = Field(..., description="Error timestamp")
