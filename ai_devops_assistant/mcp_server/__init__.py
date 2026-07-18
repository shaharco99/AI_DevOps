"""MCP protocol surface over the shared tool registry."""

from ai_devops_assistant.mcp_server.adapters import (
    build_tool_callable,
    describe_tool,
    register_registry_tools,
)

__all__ = ["build_tool_callable", "describe_tool", "register_registry_tools"]
