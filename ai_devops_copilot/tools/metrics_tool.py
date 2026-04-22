"""Metrics query tool for Prometheus."""

import logging
from typing import Any, Optional

import httpx

from ai_devops_copilot.config.settings import settings
from ai_devops_copilot.tools.base import BaseTool

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
            # Validate query
            if not query or not isinstance(query, str):
                return {
                    "success": False,
                    "error": "Invalid query",
                }

            # Execute instant query
            results = await self._instant_query(query)
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
                if data["status"] != "success":
                    return {
                        "success": False,
                        "error": data.get("error", "Unknown error"),
                    }

                # Format results
                results = data.get("data", {}).get("result", [])
                formatted_results = self._format_results(results)

                return {
                    "success": True,
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
        """Format Prometheus results."""
        formatted = []
        for result in results:
            metric = result.get("metric", {})
            value = result.get("value", [None, None])
            formatted.append({
                "metric": metric,
                "value": float(value[1]) if value[1] else None,
                "timestamp": value[0],
            })
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
