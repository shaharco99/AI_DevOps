"""Pipeline status tool with support for multiple CI/CD providers."""

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Optional

import aiohttp

from ai_devops_assistant.tools.base import BaseTool

logger = logging.getLogger(__name__)


class PipelineProvider(ABC):
    """Abstract base class for CI/CD pipeline providers."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def get_recent_builds(self, pipeline_name: Optional[str] = None) -> dict[str, Any]:
        """Get recent pipeline builds."""
        pass

    @abstractmethod
    async def get_build_logs(self, build_id: str) -> dict[str, Any]:
        """Get logs for a specific build."""
        pass

    @abstractmethod
    async def get_build_details(self, build_id: str) -> dict[str, Any]:
        """Get detailed information about a specific build."""
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if the provider is properly configured."""
        pass


class AzureDevOpsProvider(PipelineProvider):
    """Azure DevOps pipeline provider."""

    def __init__(self):
        super().__init__("azure_devops")
        self.base_url = os.getenv("AZURE_DEVOPS_URL", "https://dev.azure.com")
        self.organization = os.getenv("AZURE_DEVOPS_ORG")
        self.project = os.getenv("AZURE_DEVOPS_PROJECT")
        self.pat = os.getenv("AZURE_DEVOPS_PAT")

    def is_configured(self) -> bool:
        return all([self.organization, self.project, self.pat])

    async def get_recent_builds(self, pipeline_name: Optional[str] = None) -> dict[str, Any]:
        """Get recent pipeline builds."""
        if not self.is_configured():
            return {
                "success": False,
                "error": "Azure DevOps configuration missing. Set AZURE_DEVOPS_ORG, AZURE_DEVOPS_PROJECT, and AZURE_DEVOPS_PAT environment variables.",
            }

        url = f"{self.base_url}/{self.organization}/{self.project}/_apis/build/builds"

        params = {"api-version": "7.1", "$top": "10", "$orderby": "finishTime desc"}

        if pipeline_name:
            pipeline_id = await self._get_pipeline_id(pipeline_name)
            if pipeline_id:
                params["definitions"] = str(pipeline_id)

        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Basic {self._get_auth_token()}",
                "Content-Type": "application/json",
            }

            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    builds = []
                    for build in data.get("value", []):
                        builds.append(
                            {
                                "id": str(build["id"]),
                                "buildNumber": build["buildNumber"],
                                "status": build["status"],
                                "result": build.get("result"),
                                "startTime": build.get("startTime"),
                                "finishTime": build.get("finishTime"),
                                "sourceBranch": build.get("sourceBranch"),
                                "sourceVersion": build.get("sourceVersion"),
                                "definition": {
                                    "name": build["definition"]["name"],
                                    "id": build["definition"]["id"],
                                },
                            }
                        )

                    return {
                        "success": True,
                        "builds": builds,
                        "count": len(builds),
                    }
                else:
                    error_text = await response.text()
                    return {
                        "success": False,
                        "error": f"Azure DevOps API error: {response.status} - {error_text}",
                    }

    async def get_build_logs(self, build_id: str) -> dict[str, Any]:
        """Get logs for a specific build."""
        if not self.is_configured():
            return {
                "success": False,
                "error": "Azure DevOps configuration missing.",
            }

        # First get build timeline to find failed tasks
        timeline_url = f"{self.base_url}/{self.organization}/{self.project}/_apis/build/builds/{build_id}/timeline"

        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Basic {self._get_auth_token()}",
                "Content-Type": "application/json",
            }

            async with session.get(
                timeline_url, headers=headers, params={"api-version": "7.1"}
            ) as response:
                if response.status == 200:
                    timeline = await response.json()

                    # Find failed tasks
                    failed_tasks = []
                    for record in timeline.get("records", []):
                        if record.get("result") == "failed":
                            failed_tasks.append(
                                {
                                    "name": record.get("name"),
                                    "type": record.get("type"),
                                    "startTime": record.get("startTime"),
                                    "finishTime": record.get("finishTime"),
                                    "log_url": f"{self.base_url}/{self.organization}/{self.project}/_apis/build/builds/{build_id}/logs/{record.get('log', {}).get('id')}",
                                }
                            )

                    return {
                        "success": True,
                        "build_id": build_id,
                        "failed_tasks": failed_tasks,
                        "timeline_url": timeline_url,
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Failed to get build timeline: {response.status}",
                    }

    async def get_build_details(self, build_id: str) -> dict[str, Any]:
        """Get detailed information about a specific build."""
        if not self.is_configured():
            return {
                "success": False,
                "error": "Azure DevOps configuration missing.",
            }

        url = f"{self.base_url}/{self.organization}/{self.project}/_apis/build/builds/{build_id}"

        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Basic {self._get_auth_token()}",
                "Content-Type": "application/json",
            }

            async with session.get(url, headers=headers, params={"api-version": "7.1"}) as response:
                if response.status == 200:
                    build = await response.json()
                    return {
                        "success": True,
                        "build": {
                            "id": str(build["id"]),
                            "buildNumber": build["buildNumber"],
                            "status": build["status"],
                            "result": build.get("result"),
                            "startTime": build.get("startTime"),
                            "finishTime": build.get("finishTime"),
                            "sourceBranch": build.get("sourceBranch"),
                            "sourceVersion": build.get("sourceVersion"),
                            "reason": build.get("reason"),
                            "requestedBy": build.get("requestedBy", {}).get("displayName"),
                            "definition": build["definition"]["name"],
                            "web_url": f"{self.base_url}/{self.organization}/{self.project}/_build/results?buildId={build_id}",
                        },
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Failed to get build details: {response.status}",
                    }

    async def _get_pipeline_id(self, pipeline_name: str) -> Optional[int]:
        """Get pipeline definition ID by name."""
        url = f"{self.base_url}/{self.organization}/{self.project}/_apis/build/definitions"

        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Basic {self._get_auth_token()}",
                "Content-Type": "application/json",
            }

            async with session.get(
                url, headers=headers, params={"api-version": "7.1", "name": pipeline_name}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    definitions = data.get("value", [])
                    if definitions:
                        return definitions[0]["id"]
                return None

    def _get_auth_token(self) -> str:
        """Get base64 encoded auth token."""
        import base64

        token = f":{self.pat}"
        return base64.b64encode(token.encode()).decode()


class JenkinsProvider(PipelineProvider):
    """Jenkins pipeline provider."""

    def __init__(self):
        super().__init__("jenkins")
        self.base_url = os.getenv("JENKINS_URL", "http://localhost:8080")
        self.username = os.getenv("JENKINS_USER")
        self.api_token = os.getenv("JENKINS_API_TOKEN")

    def is_configured(self) -> bool:
        return all([self.base_url, self.username, self.api_token])

    async def get_recent_builds(self, pipeline_name: Optional[str] = None) -> dict[str, Any]:
        """Get recent pipeline builds."""
        if not self.is_configured():
            return {
                "success": False,
                "error": "Jenkins configuration missing. Set JENKINS_URL, JENKINS_USER, and JENKINS_API_TOKEN environment variables.",
            }

        if pipeline_name:
            url = f"{self.base_url}/job/{pipeline_name}/api/json"
            params = {
                "tree": "builds[number,status,timestamp,duration,result,actions[causes[shortDescription],parameters[name,value]]]{0,10}"
            }
        else:
            url = f"{self.base_url}/api/json"
            params = {"tree": "jobs[name,builds[number,status,timestamp,duration,result]{0,5}]"}

        async with aiohttp.ClientSession() as session:
            auth = aiohttp.BasicAuth(self.username, self.api_token)

            async with session.get(url, auth=auth, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    if pipeline_name:
                        builds = []
                        for build in data.get("builds", []):
                            builds.append(
                                {
                                    "id": str(build["number"]),
                                    "buildNumber": str(build["number"]),
                                    "status": "completed" if build.get("result") else "inProgress",
                                    "result": build.get("result"),
                                    "startTime": build.get("timestamp"),
                                    "duration": build.get("duration"),
                                    "definition": {"name": pipeline_name},
                                }
                            )
                        return {
                            "success": True,
                            "builds": builds,
                            "count": len(builds),
                        }
                    else:
                        all_builds = []
                        for job in data.get("jobs", []):
                            for build in job.get("builds", []):
                                all_builds.append(
                                    {
                                        "id": f"{job['name']}-{build['number']}",
                                        "buildNumber": str(build["number"]),
                                        "status": "completed"
                                        if build.get("result")
                                        else "inProgress",
                                        "result": build.get("result"),
                                        "startTime": build.get("timestamp"),
                                        "duration": build.get("duration"),
                                        "definition": {"name": job["name"]},
                                    }
                                )
                        # Sort by start time descending and take top 10
                        all_builds.sort(key=lambda x: x.get("startTime", 0), reverse=True)
                        return {
                            "success": True,
                            "builds": all_builds[:10],
                            "count": len(all_builds[:10]),
                        }
                else:
                    return {
                        "success": False,
                        "error": f"Jenkins API error: {response.status}",
                    }

    async def get_build_logs(self, build_id: str) -> dict[str, Any]:
        """Get logs for a specific build."""
        if not self.is_configured():
            return {
                "success": False,
                "error": "Jenkins configuration missing.",
            }

        # For Jenkins, build_id should be in format "job_name-build_number"
        if "-" not in build_id:
            return {
                "success": False,
                "error": "Build ID must be in format 'job_name-build_number'",
            }

        job_name, build_number = build_id.rsplit("-", 1)
        url = f"{self.base_url}/job/{job_name}/{build_number}/consoleText"

        async with aiohttp.ClientSession() as session:
            auth = aiohttp.BasicAuth(self.username, self.api_token)

            async with session.get(url, auth=auth) as response:
                if response.status == 200:
                    logs = await response.text()
                    return {
                        "success": True,
                        "build_id": build_id,
                        "logs": logs,
                        "log_url": url,
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Failed to get build logs: {response.status}",
                    }

    async def get_build_details(self, build_id: str) -> dict[str, Any]:
        """Get detailed information about a specific build."""
        if not self.is_configured():
            return {
                "success": False,
                "error": "Jenkins configuration missing.",
            }

        if "-" not in build_id:
            return {
                "success": False,
                "error": "Build ID must be in format 'job_name-build_number'",
            }

        job_name, build_number = build_id.rsplit("-", 1)
        url = f"{self.base_url}/job/{job_name}/{build_number}/api/json"

        async with aiohttp.ClientSession() as session:
            auth = aiohttp.BasicAuth(self.username, self.api_token)

            async with session.get(url, auth=auth) as response:
                if response.status == 200:
                    build = await response.json()
                    return {
                        "success": True,
                        "build": {
                            "id": build_id,
                            "buildNumber": str(build["number"]),
                            "status": "completed" if build.get("result") else "inProgress",
                            "result": build.get("result"),
                            "startTime": build.get("timestamp"),
                            "duration": build.get("duration"),
                            "definition": job_name,
                            "web_url": f"{self.base_url}/job/{job_name}/{build_number}",
                            "causes": [
                                cause.get("shortDescription")
                                for cause in build.get("actions", [])
                                if cause.get("causes")
                            ],
                        },
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Failed to get build details: {response.status}",
                    }


class GitHubActionsProvider(PipelineProvider):
    """GitHub Actions pipeline provider."""

    def __init__(self):
        super().__init__("github_actions")
        self.base_url = "https://api.github.com"
        self.owner = os.getenv("GITHUB_OWNER")
        self.repo = os.getenv("GITHUB_REPO")
        self.token = os.getenv("GITHUB_TOKEN")

    def is_configured(self) -> bool:
        return all([self.owner, self.repo, self.token])

    async def get_recent_builds(self, pipeline_name: Optional[str] = None) -> dict[str, Any]:
        """Get recent workflow runs."""
        if not self.is_configured():
            return {
                "success": False,
                "error": "GitHub configuration missing. Set GITHUB_OWNER, GITHUB_REPO, and GITHUB_TOKEN environment variables.",
            }

        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/actions/runs"
        params = {"per_page": 10}

        if pipeline_name:
            # Get workflow ID by name
            workflow_id = await self._get_workflow_id(pipeline_name)
            if workflow_id:
                params["workflow_id"] = workflow_id

        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    builds = []
                    for run in data.get("workflow_runs", []):
                        builds.append(
                            {
                                "id": str(run["id"]),
                                "buildNumber": str(run["run_number"]),
                                "status": run["status"],
                                "conclusion": run["conclusion"],
                                "startTime": run.get("created_at"),
                                "finishTime": run.get("updated_at"),
                                "sourceBranch": run.get("head_branch"),
                                "sourceVersion": run.get("head_sha"),
                                "definition": {"name": run["name"], "id": run["workflow_id"]},
                            }
                        )

                    return {
                        "success": True,
                        "builds": builds,
                        "count": len(builds),
                    }
                else:
                    error_text = await response.text()
                    return {
                        "success": False,
                        "error": f"GitHub API error: {response.status} - {error_text}",
                    }

    async def get_build_logs(self, build_id: str) -> dict[str, Any]:
        """Get logs for a specific workflow run."""
        if not self.is_configured():
            return {
                "success": False,
                "error": "GitHub configuration missing.",
            }

        # Get jobs for the run
        jobs_url = f"{self.base_url}/repos/{self.owner}/{self.repo}/actions/runs/{build_id}/jobs"

        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(jobs_url, headers=headers) as response:
                if response.status == 200:
                    jobs_data = await response.json()

                    failed_jobs = []
                    for job in jobs_data.get("jobs", []):
                        if job.get("conclusion") == "failure":
                            failed_jobs.append(
                                {
                                    "name": job.get("name"),
                                    "status": job.get("status"),
                                    "conclusion": job.get("conclusion"),
                                    "startTime": job.get("started_at"),
                                    "finishTime": job.get("completed_at"),
                                    "log_url": f"{self.base_url}/repos/{self.owner}/{self.repo}/actions/runs/{build_id}/jobs/{job['id']}/logs",
                                }
                            )

                    return {
                        "success": True,
                        "build_id": build_id,
                        "failed_jobs": failed_jobs,
                        "jobs_url": jobs_url,
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Failed to get workflow jobs: {response.status}",
                    }

    async def get_build_details(self, build_id: str) -> dict[str, Any]:
        """Get detailed information about a specific workflow run."""
        if not self.is_configured():
            return {
                "success": False,
                "error": "GitHub configuration missing.",
            }

        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/actions/runs/{build_id}"

        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    run = await response.json()
                    return {
                        "success": True,
                        "build": {
                            "id": str(run["id"]),
                            "buildNumber": str(run["run_number"]),
                            "status": run["status"],
                            "conclusion": run["conclusion"],
                            "startTime": run.get("created_at"),
                            "finishTime": run.get("updated_at"),
                            "sourceBranch": run.get("head_branch"),
                            "sourceVersion": run.get("head_sha"),
                            "trigger": run.get("event"),
                            "actor": run.get("actor", {}).get("login"),
                            "definition": run["name"],
                            "web_url": run.get("html_url"),
                        },
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Failed to get workflow details: {response.status}",
                    }

    async def _get_workflow_id(self, workflow_name: str) -> Optional[str]:
        """Get workflow ID by name."""
        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/actions/workflows"

        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    for workflow in data.get("workflows", []):
                        if (
                            workflow["name"] == workflow_name
                            or workflow["path"].endswith(f"{workflow_name}.yml")
                            or workflow["path"].endswith(f"{workflow_name}.yaml")
                        ):
                            return str(workflow["id"])
                return None


class PipelineTool(BaseTool):
    """Tool for querying CI/CD pipeline status from multiple providers."""

    def __init__(self):
        """Initialize pipeline tool."""
        super().__init__(
            name="pipeline_status_tool",
            description="Query CI/CD pipeline status, builds, and logs from Azure DevOps, Jenkins, or GitHub Actions",
        )
        self.providers = {
            "azure_devops": AzureDevOpsProvider(),
            "jenkins": JenkinsProvider(),
            "github_actions": GitHubActionsProvider(),
        }

    async def execute(
        self,
        action: str = "get_recent_builds",
        provider: str = "azure_devops",
        pipeline_name: Optional[str] = None,
        build_id: Optional[str] = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Execute CI/CD pipeline query.

        Args:
            action: Action to perform (get_recent_builds, get_build_logs, get_build_details)
            provider: CI/CD provider (azure_devops, jenkins, github_actions)
            pipeline_name: Name of the pipeline/workflow to query
            build_id: Specific build/run ID to get details for
            **kwargs: Additional parameters

        Returns:
            dict: Pipeline information from the specified provider
        """
        if provider not in self.providers:
            return {
                "success": False,
                "error": f"Unsupported provider: {provider}. Supported: {', '.join(self.providers.keys())}",
            }

        pipeline_provider = self.providers[provider]

        try:
            if action == "get_recent_builds":
                return await pipeline_provider.get_recent_builds(pipeline_name)
            elif action == "get_build_logs" and build_id:
                return await pipeline_provider.get_build_logs(build_id)
            elif action == "get_build_details" and build_id:
                return await pipeline_provider.get_build_details(build_id)
            else:
                return {
                    "success": False,
                    "error": f"Unsupported action: {action}",
                }

        except Exception as e:
            logger.error(f"{provider} API error: {e}")
            return {
                "success": False,
                "error": f"Failed to query {provider}: {str(e)}",
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
                        "enum": ["get_recent_builds", "get_build_logs", "get_build_details"],
                        "description": "Action to perform",
                    },
                    "provider": {
                        "type": "string",
                        "enum": ["azure_devops", "jenkins", "github_actions"],
                        "description": "CI/CD provider to query",
                        "default": "azure_devops",
                    },
                    "pipeline_name": {
                        "type": "string",
                        "description": "Name of the pipeline/workflow to query (optional)",
                    },
                    "build_id": {
                        "type": "string",
                        "description": "Build/run ID for detailed queries (required for get_build_logs and get_build_details)",
                    },
                },
                "required": ["action"],
            },
        }
