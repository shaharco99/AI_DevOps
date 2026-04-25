"""Monitoring integration for AI observability with Prometheus and Grafana."""

import asyncio
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai_devops_assistant.observability.ai_observability import observability_manager

logger = logging.getLogger(__name__)


class PrometheusExporter:
    """Exports AI observability metrics to Prometheus format."""

    def __init__(self, push_gateway_url: Optional[str] = None):
        """Initialize Prometheus exporter.

        Args:
            push_gateway_url: Optional PushGateway URL for pushing metrics
        """
        self.push_gateway_url = push_gateway_url
        self._last_push = 0
        self._push_interval = 60  # Push every 60 seconds

    def get_metrics_text(self) -> str:
        """Get metrics in Prometheus text format."""
        return observability_manager.get_metrics_endpoint()

    async def push_metrics(self, job_name: str = "ai-devops-assistant") -> None:
        """Push metrics to Prometheus PushGateway."""
        if not self.push_gateway_url:
            return

        current_time = time.time()
        if current_time - self._last_push < self._push_interval:
            return  # Too soon to push again

        try:
            import requests

            metrics_text = self.get_metrics_text()
            url = f"{self.push_gateway_url}/metrics/job/{job_name}"

            response = requests.post(
                url,
                data=metrics_text,
                headers={"Content-Type": "text/plain; charset=utf-8"},
                timeout=10
            )

            if response.status_code == 200:
                self._last_push = current_time
                logger.debug("Successfully pushed metrics to Prometheus PushGateway")
            else:
                logger.error(f"Failed to push metrics: {response.status_code} - {response.text}")

        except ImportError:
            logger.warning("requests library not available for PushGateway integration")
        except Exception as e:
            logger.error(f"Error pushing metrics to PushGateway: {e}")

    def start_push_loop(self, job_name: str = "ai-devops-assistant") -> None:
        """Start background thread to periodically push metrics."""
        def push_loop():
            while True:
                asyncio.run(self.push_metrics(job_name))
                time.sleep(self._push_interval)

        thread = threading.Thread(target=push_loop, daemon=True)
        thread.start()
        logger.info("Started Prometheus metrics push loop")


class GrafanaDashboardGenerator:
    """Generates Grafana dashboards for AI observability metrics."""

    def __init__(self):
        self.template_dir = Path(__file__).parent / "grafana_templates"

    def generate_ai_observability_dashboard(self) -> Dict[str, Any]:
        """Generate a comprehensive AI observability dashboard."""
        return {
            "dashboard": {
                "title": "AI DevOps Assistant Observability",
                "tags": ["ai", "devops", "observability"],
                "timezone": "browser",
                "panels": self._generate_panels(),
                "time": {
                    "from": "now-1h",
                    "to": "now"
                },
                "timepicker": {},
                "templating": {
                    "list": [
                        {
                            "type": "query",
                            "name": "model",
                            "query": "label_values(ai_llm_latency_ms_avg, model)",
                            "label": "Model",
                            "multi": True,
                            "includeAll": True
                        }
                    ]
                },
                "annotations": {
                    "list": []
                },
                "refresh": "30s",
                "schemaVersion": 27,
                "version": 0,
                "links": []
            }
        }

    def _generate_panels(self) -> List[Dict[str, Any]]:
        """Generate dashboard panels."""
        panels = []

        # Overview row
        panels.extend(self._create_overview_panels())

        # Performance row
        panels.extend(self._create_performance_panels())

        # Errors row
        panels.extend(self._create_error_panels())

        # Token usage row
        panels.extend(self._create_token_panels())

        return panels

    def _create_overview_panels(self) -> List[Dict[str, Any]]:
        """Create overview panels."""
        return [
            {
                "id": 1,
                "title": "Total LLM Requests",
                "type": "stat",
                "targets": [{
                    "expr": "ai_llm_requests_total",
                    "refId": "A"
                }],
                "fieldConfig": {
                    "defaults": {
                        "mappings": [],
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "red", "value": 80}
                            ]
                        }
                    }
                },
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0}
            },
            {
                "id": 2,
                "title": "Current Error Rate",
                "type": "stat",
                "targets": [{
                    "expr": "ai_llm_error_rate",
                    "refId": "A"
                }],
                "fieldConfig": {
                    "defaults": {
                        "mappings": [],
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "orange", "value": 0.05},
                                {"color": "red", "value": 0.1}
                            ]
                        },
                        "unit": "percentunit"
                    }
                },
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0}
            }
        ]

    def _create_performance_panels(self) -> List[Dict[str, Any]]:
        """Create performance panels."""
        return [
            {
                "id": 3,
                "title": "Average Latency by Model",
                "type": "bargauge",
                "targets": [{
                    "expr": "ai_llm_latency_ms_avg",
                    "refId": "A",
                    "legendFormat": "{{model}}"
                }],
                "fieldConfig": {
                    "defaults": {
                        "mappings": [],
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "orange", "value": 1000},
                                {"color": "red", "value": 5000}
                            ]
                        },
                        "unit": "ms"
                    }
                },
                "gridPos": {"h": 8, "w": 24, "x": 0, "y": 8}
            },
            {
                "id": 4,
                "title": "Latency Over Time",
                "type": "graph",
                "targets": [{
                    "expr": "rate(ai_llm_latency_ms_avg[5m])",
                    "refId": "A",
                    "legendFormat": "{{model}}"
                }],
                "gridPos": {"h": 8, "w": 24, "x": 0, "y": 16}
            }
        ]

    def _create_error_panels(self) -> List[Dict[str, Any]]:
        """Create error monitoring panels."""
        return [
            {
                "id": 5,
                "title": "Error Rate Over Time",
                "type": "graph",
                "targets": [{
                    "expr": "ai_llm_error_rate",
                    "refId": "A"
                }],
                "fieldConfig": {
                    "defaults": {
                        "unit": "percentunit"
                    }
                },
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 24}
            },
            {
                "id": 6,
                "title": "Errors by Model",
                "type": "table",
                "targets": [{
                    "expr": "sum by (model) (increase(ai_llm_errors_total[1h]))",
                    "refId": "A",
                    "format": "table"
                }],
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 24}
            }
        ]

    def _create_token_panels(self) -> List[Dict[str, Any]]:
        """Create token usage panels."""
        return [
            {
                "id": 7,
                "title": "Total Tokens Used",
                "type": "stat",
                "targets": [{
                    "expr": "ai_llm_tokens_total",
                    "refId": "A"
                }],
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 32}
            },
            {
                "id": 8,
                "title": "Average Tokens per Request",
                "type": "bargauge",
                "targets": [{
                    "expr": "ai_llm_tokens_avg",
                    "refId": "A",
                    "legendFormat": "{{model}}"
                }],
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 32}
            }
        ]

    def save_dashboard(self, filename: str, dashboard: Optional[Dict[str, Any]] = None) -> None:
        """Save dashboard to JSON file."""
        if dashboard is None:
            dashboard = self.generate_ai_observability_dashboard()

        output_path = Path(filename)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(dashboard, f, indent=2)

        logger.info(f"Grafana dashboard saved to {output_path}")


class HealthCheckEndpoint:
    """Provides health check endpoints for monitoring systems."""

    def __init__(self):
        self.start_time = time.time()

    def get_health(self) -> Dict[str, Any]:
        """Get comprehensive health status."""
        health_status = observability_manager.get_health_status()

        return {
            "status": health_status["status"],
            "timestamp": time.time(),
            "uptime_seconds": time.time() - self.start_time,
            "version": "1.0.0",  # Should be configurable
            "observability": health_status,
        }

    def get_liveness(self) -> Dict[str, Any]:
        """Kubernetes liveness probe endpoint."""
        # Simple liveness check - if we can respond, we're alive
        return {
            "status": "alive",
            "timestamp": time.time(),
        }

    def get_readiness(self) -> Dict[str, Any]:
        """Kubernetes readiness probe endpoint."""
        health = self.get_health()

        # Ready if health status is not unhealthy
        is_ready = health["status"] != "unhealthy"

        return {
            "status": "ready" if is_ready else "not_ready",
            "timestamp": time.time(),
            "health_status": health["status"],
        }


class MonitoringIntegration:
    """Central integration point for all monitoring systems."""

    def __init__(
        self,
        prometheus_pushgateway_url: Optional[str] = None,
        enable_push_loop: bool = True,
    ):
        """Initialize monitoring integration.

        Args:
            prometheus_pushgateway_url: URL for Prometheus PushGateway
            enable_push_loop: Whether to start automatic metrics pushing
        """
        self.prometheus_exporter = PrometheusExporter(prometheus_pushgateway_url)
        self.grafana_generator = GrafanaDashboardGenerator()
        self.health_check = HealthCheckEndpoint()

        if enable_push_loop and prometheus_pushgateway_url:
            self.prometheus_exporter.start_push_loop()

    def generate_grafana_dashboard(self, output_file: str = "grafana_dashboard.json") -> None:
        """Generate and save Grafana dashboard."""
        self.grafana_generator.save_dashboard(output_file)

    def get_prometheus_metrics(self) -> str:
        """Get current Prometheus metrics."""
        return self.prometheus_exporter.get_metrics_text()

    def get_health_status(self) -> Dict[str, Any]:
        """Get health check status."""
        return self.health_check.get_health()

    def get_liveness_status(self) -> Dict[str, Any]:
        """Get liveness probe status."""
        return self.health_check.get_liveness()

    def get_readiness_status(self) -> Dict[str, Any]:
        """Get readiness probe status."""
        return self.health_check.get_readiness()


# Global monitoring instance
monitoring_integration = MonitoringIntegration()


# CLI integration functions
def setup_monitoring_from_env() -> None:
    """Setup monitoring from environment variables."""
    import os

    pushgateway_url = os.getenv("PROMETHEUS_PUSHGATEWAY_URL")
    enable_push = os.getenv("ENABLE_PROMETHEUS_PUSH", "false").lower() == "true"

    global monitoring_integration
    monitoring_integration = MonitoringIntegration(
        prometheus_pushgateway_url=pushgateway_url,
        enable_push_loop=enable_push
    )

    if pushgateway_url:
        logger.info(f"Monitoring integration initialized with PushGateway: {pushgateway_url}")
    else:
        logger.info("Monitoring integration initialized (no PushGateway)")


# Initialize on import if environment variables are set
try:
    setup_monitoring_from_env()
except Exception as e:
    logger.warning(f"Failed to initialize monitoring from environment: {e}")
