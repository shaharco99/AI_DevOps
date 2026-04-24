"""Kubernetes tool for querying cluster state."""

import logging
from typing import Any, Optional

from kubernetes import client, config
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

            self.v1 = client.CoreV1Api()
            self.apps_v1 = client.AppsV1Api()
            self._initialized = True
            logger.info("Kubernetes client initialized")

        except Exception as e:
            logger.warning(f"Failed to initialize Kubernetes client: {e}")
            self._initialized = False

    async def execute(
        self,
        action: str,
        namespace: Optional[str] = None,
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
                        "ready": pod.status.conditions[-1].status
                        if pod.status.conditions
                        else "Unknown",
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

    async def _get_pod(self, namespace: str, pod_name: Optional[str]) -> dict[str, Any]:
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
                            "ready": pod.status.container_statuses[i].ready
                            if pod.status.container_statuses
                            else False,
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

    async def _get_deployment(
        self, namespace: str, deployment_name: Optional[str]
    ) -> dict[str, Any]:
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
