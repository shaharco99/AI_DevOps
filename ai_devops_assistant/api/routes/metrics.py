"""Metrics endpoint for DevOps assistant."""

import logging

from fastapi import APIRouter, HTTPException, Response

from ai_devops_assistant.api.schemas import MetricsQueryRequest, MetricsQueryResponse
from ai_devops_assistant.observability.monitoring import monitoring_integration
from ai_devops_assistant.tools.metrics_tool import MetricsTool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.post("", response_model=MetricsQueryResponse)
async def query_metrics(
    request: MetricsQueryRequest,
) -> MetricsQueryResponse:
    """Query Prometheus metrics.

    Args:
        request: Metrics query request

    Returns:
        MetricsQueryResponse: Query results
    """
    try:
        # Initialize metrics tool
        metrics_tool = MetricsTool()

        # Execute query
        logger.info(f"Querying metrics: {request.query}")
        result = await metrics_tool.execute(
            query=request.query,
            duration=request.duration,
        )

        if not result.get("success"):
            error_detail = result.get("error", "Metrics query failed")
            status_code = 400
            if any(
                term in error_detail
                for term in [
                    "All connection attempts failed",
                    "Connection refused",
                    "Timeout",
                    "503",
                ]
            ):
                status_code = 502
            elif error_detail.startswith("Prometheus query failed: 5"):
                status_code = 502
            raise HTTPException(
                status_code=status_code,
                detail=error_detail,
            )

        return MetricsQueryResponse(
            time_series=result.get("time_series", result.get("metrics", [])),
            query_time_ms=result.get("query_time_ms", 0.0),
        )

    except Exception as e:
        logger.error(f"Metrics query error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ai/prometheus")
async def get_ai_prometheus_metrics() -> Response:
    """Get AI observability metrics in Prometheus format.

    Returns:
        Prometheus-formatted metrics text
    """
    try:
        metrics_text = monitoring_integration.get_prometheus_metrics()
        return Response(
            content=metrics_text,
            media_type="text/plain; charset=utf-8"
        )
    except Exception as e:
        logger.error(f"Error getting AI Prometheus metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ai/health")
async def get_ai_health_status() -> dict:
    """Get AI system health status.

    Returns:
        Health status information
    """
    try:
        return monitoring_integration.get_health_status()
    except Exception as e:
        logger.error(f"Error getting AI health status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ai/liveness")
async def get_ai_liveness() -> dict:
    """Kubernetes liveness probe for AI components.

    Returns:
        Liveness status
    """
    try:
        return monitoring_integration.get_liveness_status()
    except Exception as e:
        logger.error(f"Error getting AI liveness status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ai/readiness")
async def get_ai_readiness() -> dict:
    """Kubernetes readiness probe for AI components.

    Returns:
        Readiness status
    """
    try:
        return monitoring_integration.get_readiness_status()
    except Exception as e:
        logger.error(f"Error getting AI readiness status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
