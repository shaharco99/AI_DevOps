"""Guards that the merge's temporary staging area stays gone.

_legacy/ existed so the MCP merge could land without deciding every file's final
home. It is empty now; these tests stop it being resurrected, and stop the
behaviours it contained from coming back with it.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "ai_devops_assistant"


def python_sources() -> list[Path]:
    """Every shipped Python module."""
    return [path for path in PACKAGE_ROOT.rglob("*.py") if "__pycache__" not in path.parts]


def strip_comments_and_docstrings(source: str) -> str:
    """Remove comments and triple-quoted blocks.

    These modules *discuss* the dangerous patterns in their docstrings; the
    checks are about executable code, not prose describing what was removed.
    """
    source = re.sub(r'"""(?:.|\n)*?"""', "", source)
    source = re.sub(r"'''(?:.|\n)*?'''", "", source)
    return re.sub(r"#[^\n]*", "", source)


class TestLegacyDirectoryIsGone:
    def test_legacy_directory_does_not_exist(self):
        assert not (
            REPO_ROOT / "_legacy"
        ).exists(), "_legacy/ was a merge staging area and must stay empty"

    def test_nothing_imports_from_legacy(self):
        for path in python_sources():
            source = path.read_text(encoding="utf-8")
            assert "from _legacy" not in source, path
            assert "import _legacy" not in source, path


class TestDangerousLegacyBehavioursAreGone:
    """MCP's Utils.py did all of these at import or request time."""

    def test_no_module_installs_packages_at_runtime(self):
        """`pip install` from application code is remote code execution by
        dependency confusion, and it mutates the environment under production."""
        for path in python_sources():
            code = strip_comments_and_docstrings(path.read_text(encoding="utf-8"))
            assert "pip', 'install'" not in code, path
            assert '"pip", "install"' not in code, path
            assert "pip install" not in code.replace("$ pip install", ""), path

    def test_no_module_prompts_for_input_interactively(self):
        """A server has no terminal; input() blocks the process forever."""
        for path in python_sources():
            code = strip_comments_and_docstrings(path.read_text(encoding="utf-8"))
            assert not re.search(r"\binput\s*\(", code), path
            assert "getpass" not in code, path

    def test_no_module_writes_secrets_to_a_dotenv_file(self):
        """Utils.get_api_key appended the key it had just prompted for to .env."""
        for path in python_sources():
            code = strip_comments_and_docstrings(path.read_text(encoding="utf-8"))
            assert "open('.env'" not in code, path
            assert 'open(".env"' not in code, path


class TestPortedSystemPrompt:
    """The one thing worth keeping from Utils.py."""

    @pytest.fixture
    def prompt_path(self):
        return REPO_ROOT / "prompts" / "system" / "devops_assistant_v2.0.md"

    def test_the_prompt_was_ported(self, prompt_path):
        assert prompt_path.exists()

    def test_it_has_the_frontmatter_prompt_manager_expects(self, prompt_path):
        text = prompt_path.read_text(encoding="utf-8")
        assert text.startswith("---")
        for field in ("name:", "version:", "category:", "status:"):
            assert field in text, field

    def test_it_kept_the_operational_guidance_that_made_it_worth_porting(self, prompt_path):
        text = prompt_path.read_text(encoding="utf-8")
        assert "Database Query Workflow" in text
        assert "When to Use Which Tool" in text
        assert "Limitations" in text

    def test_f_string_placeholders_became_jinja_variables(self, prompt_path):
        """It was an f-string; prompt_manager renders Jinja2."""
        text = prompt_path.read_text(encoding="utf-8")
        assert "{{ db_tools_text }}" in text
        assert "{db_tools_text}" not in text.replace("{{ db_tools_text }}", "")

    def test_prompt_manager_can_load_it(self, prompt_path):
        from ai_devops_assistant.agents.prompt_manager import PromptManager

        manager = PromptManager(prompts_dir=str(REPO_ROOT / "prompts"))
        metadata = manager.get_prompt_metadata("devops_assistant", version="2.0")
        # Metadata parsing is best-effort; the file loading is the contract.
        assert manager.load_prompt_text("devops_assistant", version="2.0")
        if metadata:
            assert metadata.name == "devops_assistant"
