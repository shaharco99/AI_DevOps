# ADR-0002: the MCP server shares the REST tool registry

Date: 2026-07-18 · Status: accepted

## Context

MCP shipped a standalone FastMCP server with its own four tools, duplicating
capabilities the REST API already had. Keeping two tool definitions in sync by
hand is a guarantee they will drift.

## Decision

One `ToolRegistry`, two protocol surfaces. `mcp_server/adapters.py` registers
every registry tool with the MCP server; adding a tool to
`ToolRegistry._initialize_tools()` exposes it over REST *and* MCP with no
MCP-side edit.

This is cheap because `BaseTool` already provides what MCP needs: `get_schema()`
is the parameter contract, and `__call__` normalises exceptions so a failing
tool returns a result instead of dropping the connection.

## Consequences

The adapter must synthesise a real function signature from each tool's JSON
Schema — FastMCP rejects `**kwargs` callables because it builds its parameter
model by introspection. A permissive test double hid this: every unit test
passed while the real server registered zero tools. The double now enforces the
same constraint the library does.

The MCP *client* half is deliberately out of scope. MCP's `server_config.json`
catalogued external servers, but no code ever read it.
