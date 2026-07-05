"""Anthropic Claude LLM service integration.

Mirrors the OllamaService interface (chat/generate/health_check/close) so the
agent can switch providers via settings.LLM_PROVIDER without code changes.
"""

import logging
from typing import Optional

import anthropic

from ai_devops_assistant.config.settings import settings

logger = logging.getLogger(__name__)


class AnthropicService:
    """Anthropic Claude service wrapper (async SDK client)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = settings.ANTHROPIC_MODEL,
        max_tokens: int = settings.ANTHROPIC_MAX_TOKENS,
        timeout: int = settings.LLM_TIMEOUT,
    ):
        """Initialize Anthropic service.

        Args:
            api_key: Anthropic API key (falls back to settings / environment)
            model: Model ID (e.g. claude-opus-4-8)
            max_tokens: Max output tokens per request
            timeout: Request timeout in seconds
        """
        self.model = model
        self.max_tokens = max_tokens
        resolved_key = api_key or settings.ANTHROPIC_API_KEY
        # No explicit key still works if the environment/SDK provides credentials
        if resolved_key:
            self.client = anthropic.AsyncAnthropic(api_key=resolved_key, timeout=timeout)
        else:
            self.client = anthropic.AsyncAnthropic(timeout=timeout)

    async def health_check(self) -> bool:
        """Check that the configured model is reachable with current credentials."""
        try:
            await self.client.models.retrieve(self.model)
            return True
        except anthropic.AuthenticationError:
            logger.error("Anthropic health check failed: invalid or missing API key")
            return False
        except Exception as e:
            logger.error(f"Anthropic health check failed: {e}")
            return False

    async def chat(self, messages: list[dict[str, str]]) -> str:
        """Chat with Claude.

        Args:
            messages: List of message dicts with 'role' and 'content'.
                'system' role messages are lifted into the top-level system prompt.

        Returns:
            str: Assistant response text ("" on failure, matching OllamaService)
        """
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        chat_messages = [m for m in messages if m.get("role") != "system"]
        if not chat_messages:
            chat_messages = [{"role": "user", "content": " "}]

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system="\n\n".join(system_parts) or anthropic.NOT_GIVEN,
                messages=chat_messages,
                thinking={"type": "adaptive"},
            )
            if response.stop_reason == "refusal":
                logger.warning("Anthropic request was refused by safety classifiers")
                return ""
            return "".join(block.text for block in response.content if block.type == "text")
        except anthropic.RateLimitError as e:
            logger.error(f"Anthropic rate limited: {e}")
            return ""
        except anthropic.APIStatusError as e:
            logger.error(f"Anthropic API error {e.status_code}: {e.message}")
            return ""
        except anthropic.APIConnectionError as e:
            logger.error(f"Anthropic connection error: {e}")
            return ""
        except Exception as e:
            logger.error(f"Anthropic chat error: {e}")
            return ""

    async def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Generate text from a plain prompt (OllamaService-compatible)."""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return await self.chat(messages)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self.client.close()
