"""Tool executor and registry."""

import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ai_devops_copilot.config.settings import settings
from ai_devops_copilot.tools.base import BaseTool
from ai_devops_copilot.tools.kubernetes_tool import KubernetesTool
from ai_devops_copilot.tools.log_tool import LogAnalysisTool
from ai_devops_copilot.tools.metrics_tool import MetricsTool
from ai_devops_copilot.tools.pipeline_tool import PipelineTool
from ai_devops_copilot.tools.sql_tool import SQLQueryTool
from ai_devops_copilot.rag.retriever import get_rag_retriever

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

    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """Get tool by name."""
        return self.tools.get(tool_name)

    def list_tools(self) -> list[str]:
        """List available tool names."""
        return list(self.tools.keys())

    def get_schemas(self) -> list[dict[str, Any]]:
        """Get schemas for all tools."""
        return [tool.get_schema() for tool in self.tools.values()]

    def set_session(self, session: AsyncSession) -> None:
        """Set database session for tools that need it."""
        if "sql_query_tool" in self.tools:
            self.tools["sql_query_tool"].set_session(session)
        if "log_analysis_tool" in self.tools:
            self.tools["log_analysis_tool"].set_session(session)


class ToolExecutor:
    """Execute tools with validation and error handling."""

    def __init__(self, registry: Optional[ToolRegistry] = None):
        """Initialize executor.
        
        Args:
            registry: Tool registry (creates new if not provided)
        """
        self.registry = registry or ToolRegistry()
        self.rag_retriever = get_rag_retriever() if settings.ENABLE_RAG else None

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

    async def execute_rag_retrieval(
        self,
        query: str,
        category: Optional[str] = None,
    ) -> dict[str, Any]:
        """Execute RAG retrieval.
        
        Args:
            query: Search query
            category: Optional category filter
            
        Returns:
            dict: Retrieved documents
        """
        if not self.rag_retriever:
            return {
                "success": False,
                "error": "RAG system not enabled",
            }

        try:
            documents = self.rag_retriever.retrieve(query, category)
            context = self.rag_retriever.format_context(documents)
            return {
                "success": True,
                "documents": documents,
                "context": context,
                "count": len(documents),
            }
        except Exception as e:
            logger.error(f"RAG retrieval failed: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def get_available_tools(self) -> dict[str, str]:
        """Get available tools with descriptions."""
        tools = {}
        for name, tool in self.registry.tools.items():
            tools[name] = tool.description
        return tools


# Global instances
_tool_registry: Optional[ToolRegistry] = None
_tool_executor: Optional[ToolExecutor] = None


def get_tool_registry() -> ToolRegistry:
    """Get or create tool registry."""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry


def get_tool_executor(session: Optional[AsyncSession] = None) -> ToolExecutor:
    """Get or create tool executor."""
    global _tool_executor
    if _tool_executor is None:
        registry = get_tool_registry()
        if session:
            registry.set_session(session)
        _tool_executor = ToolExecutor(registry)
    return _tool_executor
