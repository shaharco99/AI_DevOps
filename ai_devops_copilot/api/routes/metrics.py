"""Metrics endpoint for DevOps assistant."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from ai_devops_copilot.api.schemas import MetricsQueryRequest, MetricsQueryResponse
from ai_devops_copilot.tools.metrics_tool import MetricsTool

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
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Metrics query failed"),
            )
        
        return MetricsQueryResponse(
            time_series=result["time_series"],
            query_time_ms=result["query_time_ms"],
        )
        
    except Exception as e:
        logger.error(f"Metrics query error: {e}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail=f"Metrics query failed: {str(e)}",
        )