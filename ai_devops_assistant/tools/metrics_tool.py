"""Metrics query tool for Prometheus."""

import logging
import time
from typing import Any

import httpx

from ai_devops_assistant.config.settings import settings
from ai_devops_assistant.tools.base import BaseTool

logger = logging.getLogger(__name__)


class MetricsTool(BaseTool):
    """Tool for querying Prometheus metrics."""

    def __init__(self):
        """Initialize metrics tool."""
        super().__init__(
            name="metrics_tool",
            description="Query Prometheus for system and application metrics.",
        )
        self.prometheus_url = settings.PROMETHEUS_URL
        self.timeout = settings.PROMETHEUS_TIMEOUT

    async def execute(
        self,
        query: str,
        duration: str = "1h",
        **kwargs,
    ) -> dict[str, Any]:
        """Execute Prometheus query.

        Args:
            query: PromQL query string
            duration: Duration for range queries
            **kwargs: Additional parameters

        Returns:
            dict: Query results
        """
        try:
            if not query or not isinstance(query, str):
                return {
                    "success": False,
                    "error": "Invalid query",
                }

            start_time = time.perf_counter()
            results = await self._instant_query(query)
            results["query_time_ms"] = (time.perf_counter() - start_time) * 1000
            return results

        except Exception as e:
            logger.error(f"Metrics query error: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    async def _instant_query(self, query: str) -> dict[str, Any]:
        """Execute instant Prometheus query."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.prometheus_url}/api/v1/query",
                    params={"query": query},
                )

                if response.status_code != 200:
                    return {
                        "success": False,
                        "error": f"Prometheus query failed: {response.status_code}",
                    }

                data = response.json()
                if data.get("status") != "success":
                    return {
                        "success": False,
                        "error": data.get("error", "Unknown error"),
                    }

                results = data.get("data", {}).get("result", [])
                formatted_results = self._format_results(results)

                return {
                    "success": True,
                    "time_series": formatted_results,
                    "metrics": formatted_results,
                    "count": len(formatted_results),
                }

        except Exception as e:
            logger.error(f"Instant query error: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def _format_results(self, results: list[dict]) -> list[dict]:
        """Format Prometheus query results into API time series response shape."""
        formatted = []
        for result in results:
            metric = result.get("metric", {}) or {}
            metric_name = metric.get("__name__", "unknown")
            labels = {k: v for k, v in metric.items() if k != "__name__"}
            values = []

            if "values" in result and isinstance(result["values"], list):
                for point in result["values"]:
                    if len(point) >= 2:
                        values.append(
                            {
                                "timestamp": int(float(point[0])),
                                "value": float(point[1]) if point[1] is not None else None,
                            }
                        )
            elif "value" in result and isinstance(result["value"], list):
                timestamp, value = result["value"]
                values.append(
                    {
                        "timestamp": int(float(timestamp)) if timestamp is not None else 0,
                        "value": float(value) if value is not None else None,
                    }
                )

            formatted.append(
                {
                    "metric_name": metric_name,
                    "labels": labels,
                    "values": values,
                }
            )

        return formatted

    def get_schema(self) -> dict[str, Any]:
        """Get tool schema for LLM."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "PromQL query string",
                    },
                    "duration": {
                        "type": "string",
                        "description": "Duration for range queries (e.g., '1h', '5m')",
                    },
                },
                "required": ["query"],
            },
        }
