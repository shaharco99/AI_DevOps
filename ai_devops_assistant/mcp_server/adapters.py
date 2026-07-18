"""Expose the REST API's ToolRegistry over the MCP protocol.

This is the point of the MCP server: there is one definition of each tool, and
two protocol surfaces onto it. Adding a tool to
``ToolRegistry._initialize_tools()`` makes it available over REST *and* MCP with
no further work, and the two can never drift apart because there is nothing to
keep in sync.

The adapter is thin because BaseTool already provides what MCP needs:

- ``get_schema()`` returns a JSON Schema for the parameters, which is exactly
  the shape MCP advertises to clients.
- ``__call__`` validates parameters and converts any exception into
  ``{"success": False, "error": ...}``, so a failing tool returns a result
  rather than tearing down the connection.

``register_registry_tools`` takes anything with an ``add_tool`` method rather
than importing FastMCP, which keeps this module free of protocol-library
imports and lets the tests drive it with a recorder.
"""

from __future__ import annotations

import inspect
import logging
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from ai_devops_assistant.tools.base import BaseTool
    from ai_devops_assistant.tools.tool_executor import ToolRegistry

logger = logging.getLogger(__name__)


class SupportsAddTool(Protocol):
    """The slice of a FastMCP server this adapter uses."""

    def add_tool(self, fn: Any, name: str, description: str) -> Any:  # pragma: no cover
        ...


# JSON Schema type -> Python annotation. MCP servers build their parameter models
# by introspecting the callable, so the annotations have to be real types.
_JSON_TYPE_TO_PYTHON: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _signature_from_schema(schema: dict[str, Any]) -> inspect.Signature:
    """Build a callable signature from a tool's JSON Schema parameters.

    Required properties become positional-or-keyword parameters with no default;
    optional ones default to None and are annotated Optional.
    """
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])

    parameters = []
    # Required first: a parameter without a default cannot follow one with a default.
    for name in sorted(properties, key=lambda n: (n not in required, n)):
        spec = properties[name] if isinstance(properties[name], dict) else {}
        annotation = _JSON_TYPE_TO_PYTHON.get(spec.get("type", "string"), str)

        if name in required:
            parameters.append(
                inspect.Parameter(
                    name, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=annotation
                )
            )
        else:
            parameters.append(
                inspect.Parameter(
                    name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=None,
                    annotation=annotation | None,
                )
            )

    return inspect.Signature(parameters)


def build_tool_callable(tool: BaseTool) -> Any:
    """Wrap a BaseTool as an async callable for the MCP server.

    The wrapper cannot simply take **kwargs: MCP servers reject variadic
    callables ("Functions with **kwargs are not supported as tools") because they
    derive the advertised parameter model by introspecting the signature. So the
    signature is synthesised from the tool's own get_schema(), which keeps the
    MCP surface and the REST surface describing identical parameters.

    Kept separate from registration so the wrapping can be tested on its own.
    """

    async def _invoke(*args: Any, **kwargs: Any) -> dict[str, Any]:
        # Drop unset optionals so a tool's own defaults apply rather than None.
        supplied = {k: v for k, v in kwargs.items() if v is not None}
        # BaseTool.__call__ validates and never raises, so protocol-level errors
        # stay protocol-level and tool failures are reported as data.
        return await tool(**supplied)

    try:
        schema = tool.get_schema().get("parameters") or {}
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Tool {tool.name} has an unusable schema: {e}")
        schema = {}

    signature = _signature_from_schema(schema)
    _invoke.__signature__ = signature  # type: ignore[attr-defined]
    _invoke.__annotations__ = {
        name: param.annotation for name, param in signature.parameters.items()
    }
    _invoke.__annotations__["return"] = dict
    _invoke.__name__ = tool.name
    _invoke.__doc__ = tool.description
    return _invoke


def describe_tool(tool: BaseTool) -> dict[str, Any]:
    """Return the MCP tool description for a BaseTool.

    Falls back to an empty object schema if a tool's get_schema() is malformed,
    so one bad tool cannot stop the whole server advertising the rest.
    """
    try:
        schema = tool.get_schema()
        parameters = schema.get("parameters") or {"type": "object", "properties": {}}
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Tool {tool.name} has an unusable schema: {e}")
        parameters = {"type": "object", "properties": {}}

    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": parameters,
    }


def register_registry_tools(server: SupportsAddTool, registry: ToolRegistry) -> list[str]:
    """Register every tool in the registry with an MCP server.

    Args:
        server: An object with add_tool(fn, name, description) — a FastMCP
            instance in production.
        registry: The same ToolRegistry the REST API uses.

    Returns:
        The names registered, in registration order.
    """
    registered: list[str] = []

    for name, tool in registry.tools.items():
        try:
            server.add_tool(
                build_tool_callable(tool),
                name=name,
                description=tool.description,
            )
            registered.append(name)
        except Exception as e:
            # One tool failing to register must not take the server down; the
            # remaining tools are still worth serving.
            logger.error(f"Could not register tool {name} over MCP: {e}")

    logger.info(f"Registered {len(registered)} tools over MCP: {', '.join(registered)}")
    return registered
