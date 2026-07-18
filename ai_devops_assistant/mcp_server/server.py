"""MCP protocol server.

Runs the same tools as the REST API, over MCP, so Claude Desktop and other MCP
clients can use them directly. See adapters.py for why that costs almost no code.

Deployment: the same image as the API, a different entrypoint (see __main__.py),
on port 8001. Not 8000 — that is uvicorn's, and the original MCP server hardcoded
a collision there.

Only the *server* half is implemented. MCP's client half — connecting out to
other MCP servers, which MCP's server_config.json catalogued — is deliberately
out of scope; nothing in that project ever read the file.
"""

from __future__ import annotations

import logging

from ai_devops_assistant.config.settings import settings
from ai_devops_assistant.mcp_server.adapters import register_registry_tools
from ai_devops_assistant.tools.tool_executor import get_tool_registry

logger = logging.getLogger(__name__)

SERVER_NAME = "ai-devops-assistant"


class MCPAuthError(RuntimeError):
    """Raised when the server is asked to start without a usable auth token."""


def check_auth_configuration() -> None:
    """Refuse to start unauthenticated in production.

    The MCP transport exposes tool execution — Kubernetes reads, SQL, CI data —
    so an unauthenticated listener is a remote administrative interface. In
    development the token may be omitted, and the omission is logged loudly.
    """
    if settings.MCP_AUTH_TOKEN:
        return

    message = (
        "MCP_AUTH_TOKEN is not set. The MCP server exposes tool execution and "
        "must not run unauthenticated."
    )
    if settings.is_production:
        raise MCPAuthError(message)
    logger.warning(f"{message} Continuing because this is not a production environment.")


def create_server(registry=None):
    """Build the MCP server with the shared tool registry.

    Args:
        registry: ToolRegistry to expose. Defaults to the process-wide one, which
            is the same instance the REST API serves.

    Returns:
        A configured FastMCP server.
    """
    # Imported here rather than at module scope so importing this module (as the
    # tests do) does not require the MCP protocol library to be installed.
    from fastmcp import FastMCP

    check_auth_configuration()

    server = FastMCP(SERVER_NAME)
    registered = register_registry_tools(server, registry or get_tool_registry())

    if not registered:
        # Every tool is behind an ENABLE_* flag; all-off is a misconfiguration
        # worth flagging rather than silently serving nothing.
        logger.warning("MCP server started with no tools registered; check the ENABLE_* settings")

    return server


def run() -> None:
    """Run the MCP server over streamable HTTP.

    The transport is "streamable-http", not "http" — the latter is what MCP's
    original server passed and it is not a value fastmcp accepts, so that server
    could not actually start. The valid transports are stdio, streamable-http and
    sse; streamable-http is the one that serves network clients.
    """
    server = create_server()
    logger.info(f"Starting MCP server on {settings.MCP_HOST}:{settings.MCP_PORT} (streamable-http)")
    server.run(
        transport="streamable-http",
        host=settings.MCP_HOST,
        port=settings.MCP_PORT,
    )
