"""Prompt Management System.

Manages versioned, reusable prompts for the AI assistant.

Example:
    >>> from ai_devops_assistant.agents.prompt_manager import PromptManager
    >>> manager = PromptManager()
    >>> prompt = manager.load_prompt("devops_assistant", version="1.0")
    >>> rendered = manager.render_prompt(prompt, context={"issue": "high_cpu"})
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader, Template

logger = logging.getLogger(__name__)


@dataclass
class PromptMetadata:
    """Metadata for a prompt."""

    name: str
    version: str
    category: str
    description: str
    status: str  # active, draft, deprecated
    tags: list[str]
    last_updated: str
    template_vars: list[str]


class PromptManager:
    """Manages prompts with versioning and templating."""

    def __init__(self, prompts_dir: str = "./prompts"):
        """Initialize prompt manager.

        Args:
            prompts_dir: Directory containing prompts
        """
        self.prompts_dir = Path(prompts_dir)
        self.cache = {}

        # Initialize Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(self.prompts_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def load_prompt(
        self, name: str, version: Optional[str] = None
    ) -> Optional[Template]:
        """Load a prompt template.

        Args:
            name: Prompt name (e.g., "devops_assistant")
            version: Specific version to load, or latest if None

        Returns:
            Jinja2 Template or None if not found
        """
        try:
            # Build file path
            if version:
                filename = f"{name}_v{version}.md"
            else:
                # Find latest version
                filename = self._find_latest_prompt(name)

            if not filename:
                logger.error(f"Prompt not found: {name}")
                return None

            # Check cache
            cache_key = f"{name}:{version or 'latest'}"
            if cache_key in self.cache:
                return self.cache[cache_key]

            # Load from file
            template = self.env.get_template(filename)
            self.cache[cache_key] = template

            return template

        except Exception as e:
            logger.error(f"Error loading prompt {name}: {e}")
            return None

    def load_prompt_text(
        self, name: str, version: Optional[str] = None
    ) -> Optional[str]:
        """Load raw prompt text without templating.

        Args:
            name: Prompt name
            version: Specific version

        Returns:
            Raw prompt text or None
        """
        try:
            if version:
                filename = f"{name}_v{version}.md"
            else:
                filename = self._find_latest_prompt(name)

            if not filename:
                return None

            filepath = self.prompts_dir / filename
            with open(filepath, "r") as f:
                return f.read()

        except Exception as e:
            logger.error(f"Error loading prompt text: {e}")
            return None

    def render_prompt(
        self,
        template_or_name: str | Template,
        context: dict[str, Any],
        version: Optional[str] = None,
    ) -> str:
        """Render a prompt with context variables.

        Args:
            template_or_name: Template object or prompt name
            context: Variables to render
            version: If using name, version to load

        Returns:
            Rendered prompt string
        """
        try:
            # Get template
            if isinstance(template_or_name, str):
                template = self.load_prompt(template_or_name, version)
                if not template:
                    return ""
            else:
                template = template_or_name

            # Render with context
            return template.render(**context)

        except Exception as e:
            logger.error(f"Error rendering prompt: {e}")
            return ""

    def get_prompt_metadata(
        self, name: str, version: Optional[str] = None
    ) -> Optional[PromptMetadata]:
        """Get metadata for a prompt.

        Args:
            name: Prompt name
            version: Specific version

        Returns:
            PromptMetadata or None
        """
        try:
            text = self.load_prompt_text(name, version)
            if not text:
                return None

            # Parse YAML front matter
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 2:
                    metadata_str = parts[1]
                    return self._parse_metadata(metadata_str, name, version)

            return None

        except Exception as e:
            logger.error(f"Error getting metadata: {e}")
            return None

    def _parse_metadata(
        self, metadata_str: str, name: str, version: Optional[str]
    ) -> Optional[PromptMetadata]:
        """Parse YAML metadata.

        Args:
            metadata_str: YAML metadata block
            name: Prompt name
            version: Version

        Returns:
            PromptMetadata or None
        """
        try:
            # Simple YAML parsing (not using yaml library to avoid dependency)
            metadata = {}
            for line in metadata_str.strip().split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip().lower()
                    value = value.strip()

                    if key == "tags":
                        value = [v.strip() for v in value.strip("[]").split(",")]
                    elif key == "version":
                        version = value

                    metadata[key] = value

            return PromptMetadata(
                name=name,
                version=version or "1.0",
                category=metadata.get("category", "general"),
                description=metadata.get("description", ""),
                status=metadata.get("status", "active"),
                tags=metadata.get("tags", []),
                last_updated=metadata.get("last_updated", ""),
                template_vars=self._extract_template_vars(metadata_str),
            )

        except Exception as e:
            logger.warning(f"Error parsing metadata: {e}")
            return None

    def _extract_template_vars(self, text: str) -> list[str]:
        """Extract Jinja2 template variables.

        Args:
            text: Template text

        Returns:
            List of variable names
        """
        # Find {{ variable }} patterns
        pattern = r"\{\{(.*?)\}\}"
        matches = re.findall(pattern, text)

        # Clean up and deduplicate
        vars_set = set()
        for match in matches:
            var = match.strip().split("|")[0].split(".")[0].strip()
            if var:
                vars_set.add(var)

        return sorted(list(vars_set))

    def list_prompts(self, category: Optional[str] = None) -> list[str]:
        """List available prompts.

        Args:
            category: Filter by category (system, rag, agents, tools)

        Returns:
            List of prompt names
        """
        try:
            prompts = set()

            for filepath in self.prompts_dir.glob("**/*.md"):
                # Skip README
                if filepath.name == "README.md":
                    continue

                # Extract name (remove version suffix)
                name = filepath.stem
                name = re.sub(r"_v[\d.]+$", "", name)

                if category:
                    # Check if prompt is in category subdirectory
                    if category in filepath.parts:
                        prompts.add(name)
                else:
                    prompts.add(name)

            return sorted(list(prompts))

        except Exception as e:
            logger.error(f"Error listing prompts: {e}")
            return []

    def save_prompt(
        self,
        name: str,
        content: str,
        version: str = "1.0",
        category: str = "general",
        metadata: Optional[dict] = None,
    ) -> bool:
        """Save a new prompt.

        Args:
            name: Prompt name
            content: Prompt content
            version: Version number
            category: Prompt category
            metadata: Additional metadata

        Returns:
            True if successful
        """
        try:
            # Create directory if needed
            category_dir = self.prompts_dir / category
            category_dir.mkdir(parents=True, exist_ok=True)

            # Create metadata block
            meta = metadata or {}
            meta.setdefault("version", version)
            meta.setdefault("status", "active")
            meta.setdefault("category", category)

            metadata_block = "---\n"
            for key, value in meta.items():
                if isinstance(value, list):
                    value_str = ", ".join(value)
                    metadata_block += f"{key}: [{value_str}]\n"
                else:
                    metadata_block += f"{key}: {value}\n"
            metadata_block += "---\n\n"

            # Write file
            filename = f"{name}_v{version}.md"
            filepath = category_dir / filename

            with open(filepath, "w") as f:
                f.write(metadata_block + content)

            logger.info(f"Prompt saved: {filepath}")
            return True

        except Exception as e:
            logger.error(f"Error saving prompt: {e}")
            return False

    def _find_latest_prompt(self, name: str) -> Optional[str]:
        """Find the latest version of a prompt.

        Args:
            name: Prompt name

        Returns:
            Filename or None
        """
        try:
            # Search for prompt files matching the name
            matches = list(self.prompts_dir.glob(f"**/{name}_v*.md"))

            if not matches:
                # Try without version suffix
                matches = list(self.prompts_dir.glob(f"**/{name}.md"))

            if not matches:
                return None

            # Sort by version (if versioned)
            def get_version(path):
                match = re.search(r"_v([\d.]+)", path.stem)
                if match:
                    parts = match.group(1).split(".")
                    return tuple(int(p) for p in parts)
                return (0,)

            latest = sorted(matches, key=get_version, reverse=True)[0]
            return latest.name

        except Exception as e:
            logger.error(f"Error finding latest prompt: {e}")
            return None
