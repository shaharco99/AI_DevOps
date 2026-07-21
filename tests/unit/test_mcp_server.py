"""Unit tests for the MCP protocol surface.

The property under test is the architectural one: MCP and REST serve the *same*
ToolRegistry, so they cannot drift apart. Several tests assert that equality
directly, and one asserts the deleted RCE stays deleted.
"""

import inspect
from unittest.mock import MagicMock, patch

import pytest

from ai_devops_assistant.config.settings import settings
from ai_devops_assistant.mcp_server.adapters import (
    build_tool_callable,
    describe_tool,
    register_registry_tools,
)
from ai_devops_assistant.mcp_server.server import MCPAuthError, check_auth_configuration
from ai_devops_assistant.tools.base import BaseTool


class RecordingServer:
    """Stands in for FastMCP, recording what would be registered.

    It enforces FastMCP's actual constraints rather than accepting anything. An
    earlier, permissive version of this double let every test pass while the real
    server registered *zero* tools, because FastMCP rejects callables that take
    **kwargs and the wrapper used them. A double that is more forgiving than the
    real thing is worse than no double at all.
    """

    def __init__(self, fail_on: str | None = None):
        self.registered: list[dict] = []
        self.fail_on = fail_on

    def add_tool(self, fn, name: str, description: str):
        if name == self.fail_on:
            raise RuntimeError(f"simulated registration failure for {name}")

        # FastMCP builds its parameter model by introspecting the callable, so a
        # variadic signature is rejected outright.
        signature = inspect.signature(fn)
        for parameter in signature.parameters.values():
            if parameter.kind is inspect.Parameter.VAR_KEYWORD:
                raise ValueError("Functions with **kwargs are not supported as tools")
            if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
                raise ValueError("Functions with *args are not supported as tools")

        self.registered.append(
            {"fn": fn, "name": name, "description": description, "signature": signature}
        )

    @property
    def names(self) -> list[str]:
        return [entry["name"] for entry in self.registered]


class DummyTool(BaseTool):
    """A minimal BaseTool for adapter tests."""

    def __init__(self, name="dummy_tool", result=None, raises=None):
        super().__init__(name=name, description=f"Description of {name}")
        self._result = result or {"success": True, "value": 42}
        self._raises = raises

    async def execute(self, **kwargs):
        if self._raises:
            raise self._raises
        return {**self._result, "received": kwargs}

    def get_schema(self):
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }


def make_registry(*tools):
    registry = MagicMock()
    registry.tools = {tool.name: tool for tool in tools}
    return registry


class TestDescribeTool:
    def test_uses_the_tools_own_schema(self):
        described = describe_tool(DummyTool())
        assert described["name"] == "dummy_tool"
        assert described["parameters"]["properties"]["query"]["type"] == "string"

    def test_falls_back_to_an_empty_schema_when_get_schema_breaks(self):
        """One malformed tool must not stop the server advertising the rest."""
        tool = DummyTool()
        tool.get_schema = MagicMock(side_effect=ValueError("bad schema"))
        described = describe_tool(tool)
        assert described["parameters"] == {"type": "object", "properties": {}}


class TestBuildToolCallable:
    @pytest.mark.asyncio
    async def test_the_callable_invokes_the_tool(self):
        fn = build_tool_callable(DummyTool())
        result = await fn(query="hello")
        assert result["success"] is True
        assert result["received"] == {"query": "hello"}

    @pytest.mark.asyncio
    async def test_a_failing_tool_returns_an_error_instead_of_raising(self):
        """BaseTool.__call__ normalises exceptions, so the connection survives."""
        fn = build_tool_callable(DummyTool(raises=RuntimeError("tool exploded")))
        result = await fn(query="x")
        assert result["success"] is False
        assert "tool exploded" in result["error"]

    def test_the_callable_carries_the_tools_name_and_description(self):
        fn = build_tool_callable(DummyTool(name="kubernetes_tool"))
        assert fn.__name__ == "kubernetes_tool"
        assert "kubernetes_tool" in fn.__doc__

    def test_the_signature_is_not_variadic(self):
        """The bug this caught: a **kwargs wrapper registers zero tools.

        FastMCP introspects the callable to build its parameter model and rejects
        variadic signatures outright, so every tool silently failed to register
        while the unit tests passed against a permissive double.
        """
        fn = build_tool_callable(DummyTool())
        kinds = {p.kind for p in inspect.signature(fn).parameters.values()}
        assert inspect.Parameter.VAR_KEYWORD not in kinds
        assert inspect.Parameter.VAR_POSITIONAL not in kinds

    def test_the_signature_mirrors_the_tools_schema(self):
        fn = build_tool_callable(DummyTool())
        parameters = inspect.signature(fn).parameters
        assert list(parameters) == ["query"]
        assert parameters["query"].annotation is str
        assert parameters["query"].default is inspect.Parameter.empty, "required param"

    def test_optional_parameters_get_a_none_default(self):
        from ai_devops_assistant.tools.sql_tool import SQLQueryTool

        parameters = inspect.signature(build_tool_callable(SQLQueryTool())).parameters
        assert parameters["query"].default is inspect.Parameter.empty
        assert parameters["limit"].default is None

    def test_required_parameters_precede_optional_ones(self):
        """Otherwise the synthesised signature is not constructible at all."""
        from ai_devops_assistant.tools.tool_executor import get_tool_registry

        for name, tool in get_tool_registry().tools.items():
            seen_default = False
            for param in inspect.signature(build_tool_callable(tool)).parameters.values():
                if param.default is not inspect.Parameter.empty:
                    seen_default = True
                elif seen_default:
                    raise AssertionError(f"{name}: required param follows an optional one")

    @pytest.mark.asyncio
    async def test_unset_optionals_are_not_passed_to_the_tool(self):
        """Passing limit=None would override the tool's own default."""
        tool = DummyTool()
        fn = build_tool_callable(tool)
        result = await fn(query="x")
        assert result["received"] == {"query": "x"}

    def test_every_registry_tool_produces_a_registrable_callable(self):
        """End-to-end guard: all real tools must survive MCP registration."""
        from ai_devops_assistant.tools.tool_executor import get_tool_registry

        server = RecordingServer()
        registry = get_tool_registry()
        registered = register_registry_tools(server, registry)
        assert len(registered) == len(registry.tools), "some tools failed to register"


class TestRegisterRegistryTools:
    def test_registers_every_tool_in_the_registry(self):
        server = RecordingServer()
        registry = make_registry(DummyTool("a"), DummyTool("b"), DummyTool("c"))

        registered = register_registry_tools(server, registry)

        assert registered == ["a", "b", "c"]
        assert server.names == ["a", "b", "c"]

    def test_passes_each_tools_description_through(self):
        server = RecordingServer()
        register_registry_tools(server, make_registry(DummyTool("a")))
        assert server.registered[0]["description"] == "Description of a"

    def test_one_failing_registration_does_not_stop_the_others(self):
        server = RecordingServer(fail_on="b")
        registry = make_registry(DummyTool("a"), DummyTool("b"), DummyTool("c"))

        registered = register_registry_tools(server, registry)

        assert registered == ["a", "c"]
        assert "b" not in server.names

    def test_an_empty_registry_registers_nothing_without_error(self):
        server = RecordingServer()
        assert register_registry_tools(server, make_registry()) == []


class TestOneRegistryTwoSurfaces:
    """The architectural claim, asserted rather than described."""

    def test_mcp_exposes_exactly_the_rest_registry(self):
        from ai_devops_assistant.tools.tool_executor import get_tool_registry

        registry = get_tool_registry()
        server = RecordingServer()
        registered = register_registry_tools(server, registry)

        assert set(registered) == set(
            registry.tools
        ), "MCP and REST must expose the same tools; a difference means they have drifted"

    def test_adding_a_tool_to_the_registry_exposes_it_over_mcp(self):
        """No MCP-side edit is needed for a new tool — that is the whole point."""
        registry = make_registry(DummyTool("existing"))
        server_before = RecordingServer()
        register_registry_tools(server_before, registry)
        assert server_before.names == ["existing"]

        registry.tools["brand_new_tool"] = DummyTool("brand_new_tool")
        server_after = RecordingServer()
        register_registry_tools(server_after, registry)

        assert "brand_new_tool" in server_after.names

    def test_mcp_schemas_match_the_rest_schemas(self):
        from ai_devops_assistant.tools.tool_executor import get_tool_registry

        registry = get_tool_registry()
        for name, tool in registry.tools.items():
            assert describe_tool(tool)["parameters"] == tool.get_schema()["parameters"], name


class TestAuthConfiguration:
    def test_production_without_a_token_refuses_to_start(self):
        """The MCP transport executes tools; unauthenticated is a remote admin API."""
        with (
            patch.object(settings, "MCP_AUTH_TOKEN", None),
            patch.object(settings, "API_ENVIRONMENT", "production"),
        ):
            with pytest.raises(MCPAuthError) as exc:
                check_auth_configuration()
        assert "MCP_AUTH_TOKEN" in str(exc.value)

    def test_production_with_a_token_is_allowed(self):
        with (
            patch.object(settings, "MCP_AUTH_TOKEN", "a-real-token"),
            patch.object(settings, "API_ENVIRONMENT", "production"),
        ):
            check_auth_configuration()  # must not raise

    def test_development_without_a_token_warns_but_continues(self, caplog):
        with (
            patch.object(settings, "MCP_AUTH_TOKEN", None),
            patch.object(settings, "API_ENVIRONMENT", "development"),
        ):
            check_auth_configuration()
        assert any("MCP_AUTH_TOKEN" in record.message for record in caplog.records)

    def test_the_token_is_not_set_by_default(self):
        assert settings.MCP_AUTH_TOKEN is None


class TestDeletedRce:
    """The legacy server ran `python -c <arbitrary string>` with no guard."""

    def test_run_python_script_is_gone(self):
        import ai_devops_assistant.mcp_server as pkg

        source_dir = __import__("pathlib").Path(pkg.__file__).parent
        for path in source_dir.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert "run_python_script" not in source, f"the RCE reappeared in {path.name}"

    def test_the_mcp_package_never_shells_out(self):
        """Command execution belongs in ShellTool, behind its allowlist."""
        import ai_devops_assistant.mcp_server as pkg

        source_dir = __import__("pathlib").Path(pkg.__file__).parent
        for path in source_dir.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for sink in ("subprocess.", "os.system", "eval(", "exec("):
                assert sink not in source, f"{sink} found in {path.name}"

    def test_legacy_server_module_is_deleted(self):
        with pytest.raises(ImportError):
            __import__("ai_devops_assistant.mcp_server.legacy_server")


class TestServerConstruction:
    def test_create_server_registers_the_shared_registry(self):
        from ai_devops_assistant.mcp_server import server as server_module

        registry = make_registry(DummyTool("a"), DummyTool("b"))
        with patch.object(settings, "MCP_AUTH_TOKEN", "token"):
            built = server_module.create_server(registry=registry)

        # FastMCP exposes its tools asynchronously; the observable check here is
        # that construction succeeded with the injected registry.
        assert built is not None

    def test_create_server_refuses_unauthenticated_production(self):
        from ai_devops_assistant.mcp_server import server as server_module

        with (
            patch.object(settings, "MCP_AUTH_TOKEN", None),
            patch.object(settings, "API_ENVIRONMENT", "production"),
        ):
            with pytest.raises(MCPAuthError):
                server_module.create_server(registry=make_registry(DummyTool("a")))


class TestPortSeparation:
    def test_mcp_does_not_share_the_api_port(self):
        """MCP's original server hardcoded 8000, colliding with uvicorn."""
        assert settings.MCP_PORT != settings.API_PORT
        assert settings.MCP_PORT == 8001
