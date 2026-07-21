"""Tool executor and registry."""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ai_devops_assistant.config.settings import settings
from ai_devops_assistant.tools.base import BaseTool
from ai_devops_assistant.tools.kubernetes_tool import KubernetesTool
from ai_devops_assistant.tools.log_tool import LogAnalysisTool
from ai_devops_assistant.tools.metrics_tool import MetricsTool
from ai_devops_assistant.tools.pipeline_tool import PipelineTool
from ai_devops_assistant.tools.shell_tool import ShellTool
from ai_devops_assistant.tools.sql_tool import SQLQueryTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for all available tools."""

    def __init__(self):
        """Initialize tool registry."""
        self.tools: dict[str, BaseTool] = {}
        self._initialize_tools()

    def _initialize_tools(self) -> None:
        """Initialize all available tools."""
        # SQL tool
        if settings.ENABLE_SQL_TOOL:
            self.tools["sql_query_tool"] = SQLQueryTool()

        # Shell tool. Off by default: it runs processes on the host, and
        # everything it can read is also reachable through the Kubernetes tool.
        if settings.ENABLE_SHELL_TOOL:
            self.tools["shell_tool"] = ShellTool()

        # Kubernetes tool
        if settings.ENABLE_K8S_TOOL:
            k8s_tool = KubernetesTool()
            k8s_tool.initialize()
            self.tools["kubernetes_tool"] = k8s_tool

        # Log analysis tool
        if settings.ENABLE_LOG_TOOL:
            self.tools["log_analysis_tool"] = LogAnalysisTool()

        # Metrics tool
        if settings.ENABLE_METRICS_TOOL:
            self.tools["metrics_tool"] = MetricsTool()

        # Pipeline tool
        if settings.ENABLE_PIPELINE_TOOL:
            self.tools["pipeline_status_tool"] = PipelineTool()

        logger.info(f"Tool registry initialized with {len(self.tools)} tools")

    def get_tool(self, tool_name: str) -> BaseTool | None:
        """Get tool by name."""
        return self.tools.get(tool_name)

    def list_tools(self) -> list[str]:
        """List available tool names."""
        return list(self.tools.keys())

    def get_schemas(self) -> list[dict[str, Any]]:
        """Get schemas for all tools."""
        return [tool.get_schema() for tool in self.tools.values()]

    def set_session(self, session: AsyncSession) -> None:
        """Inject the request-scoped DB session into every tool that accepts one.

        Previously this named sql_query_tool and log_analysis_tool explicitly, so a
        new DB-backed tool silently got no session until someone remembered to edit
        this method. Discovering the setter keeps that automatic. set_session is not
        on BaseTool because most tools do not need a session.
        """
        for tool in self.tools.values():
            setter = getattr(tool, "set_session", None)
            if callable(setter):
                setter(session)


class ToolExecutor:
    """Execute tools with validation and error handling."""

    def __init__(self, registry: ToolRegistry | None = None):
        """Initialize executor.

        Args:
            registry: Tool registry (creates new if not provided)
        """
        self.registry = registry or ToolRegistry()

    async def execute_tool(
        self,
        tool_name: str,
        **parameters,
    ) -> dict[str, Any]:
        """Execute a tool.

        Args:
            tool_name: Name of tool to execute
            **parameters: Tool parameters

        Returns:
            dict: Execution result
        """
        tool = self.registry.get_tool(tool_name)
        if not tool:
            return {
                "success": False,
                "error": f"Tool not found: {tool_name}",
            }

        logger.info(f"Executing tool: {tool_name}")
        return await tool(**parameters)

    def get_available_tools(self) -> dict[str, str]:
        """Get available tools with descriptions."""
        tools = {}
        for name, tool in self.registry.tools.items():
            tools[name] = tool.description
        return tools


# Global instances
_tool_registry: ToolRegistry | None = None
_tool_executor: ToolExecutor | None = None


def get_tool_registry() -> ToolRegistry:
    """Get or create tool registry."""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry


def get_tool_executor(session: AsyncSession | None = None) -> ToolExecutor:
    """Get or create tool executor."""
    global _tool_executor
    if _tool_executor is None:
        registry = get_tool_registry()
        if session:
            registry.set_session(session)
        _tool_executor = ToolExecutor(registry)
    return _tool_executor
