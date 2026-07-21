"""Kubernetes tool for querying cluster state."""

import logging
from typing import Any

from kubernetes import client, config
from kubernetes.client import Configuration
from kubernetes.client.rest import ApiException

from ai_devops_assistant.config.settings import settings
from ai_devops_assistant.tools.base import BaseTool

logger = logging.getLogger(__name__)


class KubernetesTool(BaseTool):
    """Tool for querying Kubernetes clusters."""

    def __init__(self):
        """Initialize Kubernetes tool."""
        super().__init__(
            name="kubernetes_tool",
            description="Query Kubernetes cluster for pod status, deployments, services, and events.",
        )
        self.v1 = None
        self.apps_v1 = None
        self._initialized = False

    def initialize(self) -> None:
        """Initialize Kubernetes client."""
        if self._initialized:
            return

        try:
            # Load kubeconfig
            if settings.KUBECONFIG:
                config.load_kube_config(config_file=settings.KUBECONFIG)
            else:
                config.load_incluster_config()  # For running in-cluster

            # K8S_VERIFY_SSL was declared in settings but never applied, so TLS
            # verification was simply whatever the kubeconfig said. It is applied
            # here, and disabling it is refused in production: turning off
            # verification against the cluster API exposes every request —
            # including tokens — to interception.
            if not settings.K8S_VERIFY_SSL:
                if settings.is_production:
                    raise ValueError(
                        "K8S_VERIFY_SSL=false is not permitted in production; "
                        "it disables TLS verification against the cluster API"
                    )
                logger.warning(
                    "Kubernetes TLS verification is DISABLED (K8S_VERIFY_SSL=false). "
                    "Development only."
                )
                configuration = Configuration.get_default_copy()
                configuration.verify_ssl = False
                Configuration.set_default(configuration)

            self.v1 = client.CoreV1Api()
            self.apps_v1 = client.AppsV1Api()
            self._initialized = True
            logger.info("Kubernetes client initialized")

        except Exception as e:
            logger.warning(f"Failed to initialize Kubernetes client: {e}")
            self._initialized = False

    # Narrows BaseTool.execute(**kwargs) to this tool's named parameters. The
    # registry always dispatches by keyword and validate_parameters() guards the
    # required ones, so the narrowing is deliberate; mypy cannot express it.
    async def execute(  # type: ignore[override]
        self,
        action: str,
        namespace: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Execute Kubernetes query.

        Args:
            action: Action to perform (list_pods, get_pod, list_deployments, etc.)
            namespace: Kubernetes namespace
            **kwargs: Additional parameters

        Returns:
            dict: Query results
        """
        if not self._initialized:
            return {
                "success": False,
                "error": "Kubernetes client not initialized",
            }

        namespace = namespace or settings.K8S_NAMESPACE

        try:
            if action == "list_pods":
                return await self._list_pods(namespace)
            elif action == "get_pod":
                return await self._get_pod(namespace, kwargs.get("pod_name"))
            elif action == "list_deployments":
                return await self._list_deployments(namespace)
            elif action == "get_deployment":
                return await self._get_deployment(namespace, kwargs.get("deployment_name"))
            elif action == "list_services":
                return await self._list_services(namespace)
            elif action == "list_events":
                return await self._list_events(namespace)
            elif action == "cluster_overview":
                return await self._cluster_overview(namespace)
            else:
                return {
                    "success": False,
                    "error": f"Unknown action: {action}",
                }

        except Exception as e:
            logger.error(f"Kubernetes query failed: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    async def _cluster_overview(self, namespace: str) -> dict[str, Any]:
        """Summarise the cluster: namespaces, and pods/deployments in one of them.

        Ported from MCP's standalone server, where it was the one genuinely useful
        aggregate. It answers "what am I looking at?" in a single call instead of
        three, which matters when an agent is paying per round trip.
        """
        try:
            namespaces = [n.metadata.name for n in self.v1.list_namespace().items]
            pods = [p.metadata.name for p in self.v1.list_namespaced_pod(namespace).items]
            deployments = [
                d.metadata.name for d in self.apps_v1.list_namespaced_deployment(namespace).items
            ]
            return {
                "success": True,
                "namespace": namespace,
                "namespaces": namespaces,
                "pods": pods,
                "deployments": deployments,
                "counts": {
                    "namespaces": len(namespaces),
                    "pods": len(pods),
                    "deployments": len(deployments),
                },
            }
        except ApiException as e:
            return {
                "success": False,
                "error": str(e),
            }

    async def _list_pods(self, namespace: str) -> dict[str, Any]:
        """List pods in namespace."""
        try:
            pods = self.v1.list_namespaced_pod(namespace)
            pod_list = []
            for pod in pods.items:
                pod_list.append(
                    {
                        "name": pod.metadata.name,
                        "status": pod.status.phase,
                        "ready": (
                            pod.status.conditions[-1].status if pod.status.conditions else "Unknown"
                        ),
                        "restarts": sum(
                            c.restart_count for c in pod.status.container_statuses or []
                        ),
                        "age": str(pod.metadata.creation_timestamp),
                    }
                )
            return {
                "success": True,
                "pods": pod_list,
                "count": len(pod_list),
            }
        except ApiException as e:
            return {
                "success": False,
                "error": str(e),
            }

    async def _get_pod(self, namespace: str, pod_name: str | None) -> dict[str, Any]:
        """Get specific pod details."""
        if not pod_name:
            return {
                "success": False,
                "error": "pod_name is required",
            }

        try:
            pod = self.v1.read_namespaced_pod(pod_name, namespace)
            return {
                "success": True,
                "pod": {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "status": pod.status.phase,
                    "containers": [
                        {
                            "name": c.name,
                            "image": c.image,
                            "ready": (
                                pod.status.container_statuses[i].ready
                                if pod.status.container_statuses
                                else False
                            ),
                        }
                        for i, c in enumerate(pod.spec.containers)
                    ],
                    "conditions": [
                        {
                            "type": c.type,
                            "status": c.status,
                            "message": c.message,
                        }
                        for c in (pod.status.conditions or [])
                    ],
                },
            }
        except ApiException as e:
            return {
                "success": False,
                "error": str(e),
            }

    async def _list_deployments(self, namespace: str) -> dict[str, Any]:
        """List deployments in namespace."""
        try:
            deployments = self.apps_v1.list_namespaced_deployment(namespace)
            dep_list = []
            for dep in deployments.items:
                dep_list.append(
                    {
                        "name": dep.metadata.name,
                        "desired": dep.spec.replicas,
                        "ready": dep.status.ready_replicas or 0,
                        "updated": dep.status.updated_replicas or 0,
                        "available": dep.status.available_replicas or 0,
                        "age": str(dep.metadata.creation_timestamp),
                    }
                )
            return {
                "success": True,
                "deployments": dep_list,
                "count": len(dep_list),
            }
        except ApiException as e:
            return {
                "success": False,
                "error": str(e),
            }

    async def _get_deployment(self, namespace: str, deployment_name: str | None) -> dict[str, Any]:
        """Get specific deployment details."""
        if not deployment_name:
            return {
                "success": False,
                "error": "deployment_name is required",
            }

        try:
            dep = self.apps_v1.read_namespaced_deployment(deployment_name, namespace)
            return {
                "success": True,
                "deployment": {
                    "name": dep.metadata.name,
                    "namespace": dep.metadata.namespace,
                    "replicas": dep.spec.replicas,
                    "ready_replicas": dep.status.ready_replicas or 0,
                    "updated_replicas": dep.status.updated_replicas or 0,
                    "available_replicas": dep.status.available_replicas or 0,
                    "conditions": [
                        {
                            "type": c.type,
                            "status": c.status,
                            "message": c.message,
                        }
                        for c in (dep.status.conditions or [])
                    ],
                },
            }
        except ApiException as e:
            return {
                "success": False,
                "error": str(e),
            }

    async def _list_services(self, namespace: str) -> dict[str, Any]:
        """List services in namespace."""
        try:
            services = self.v1.list_namespaced_service(namespace)
            svc_list = []
            for svc in services.items:
                svc_list.append(
                    {
                        "name": svc.metadata.name,
                        "type": svc.spec.type,
                        "cluster_ip": svc.spec.cluster_ip,
                        "ports": [
                            {
                                "name": p.name,
                                "port": p.port,
                                "target_port": p.target_port,
                            }
                            for p in (svc.spec.ports or [])
                        ],
                    }
                )
            return {
                "success": True,
                "services": svc_list,
                "count": len(svc_list),
            }
        except ApiException as e:
            return {
                "success": False,
                "error": str(e),
            }

    async def _list_events(self, namespace: str) -> dict[str, Any]:
        """List events in namespace."""
        try:
            events = self.v1.list_namespaced_event(namespace)
            event_list = []
            for event in events.items:
                event_list.append(
                    {
                        "reason": event.reason,
                        "message": event.message,
                        "type": event.type,
                        "count": event.count,
                        "timestamp": str(event.last_timestamp),
                        "involved_object": {
                            "kind": event.involved_object.kind,
                            "name": event.involved_object.name,
                        },
                    }
                )
            return {
                "success": True,
                "events": event_list,
                "count": len(event_list),
            }
        except ApiException as e:
            return {
                "success": False,
                "error": str(e),
            }

    def get_schema(self) -> dict[str, Any]:
        """Get tool schema for LLM."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "list_pods",
                            "get_pod",
                            "list_deployments",
                            "get_deployment",
                            "list_services",
                            "list_events",
                            "cluster_overview",
                        ],
                        "description": "Action to perform",
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace",
                    },
                    "pod_name": {
                        "type": "string",
                        "description": "Pod name (for get_pod action)",
                    },
                    "deployment_name": {
                        "type": "string",
                        "description": "Deployment name (for get_deployment action)",
                    },
                },
                "required": ["action"],
            },
        }
