"""Anthropic Claude LLM service integration.

Mirrors the OllamaService interface (chat/generate/health_check/close) so the
agent can switch providers via settings.LLM_PROVIDER without code changes.
"""

import logging

import anthropic
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from ai_devops_assistant.config.settings import settings
from ai_devops_assistant.services.llm_service import LLMServiceError

logger = logging.getLogger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    """Retry on rate limits, connection errors, and 5xx — not on auth/4xx."""
    if isinstance(exc, (anthropic.RateLimitError, anthropic.APIConnectionError)):
        return True
    return isinstance(exc, anthropic.APIStatusError) and exc.status_code >= 500


anthropic_retry = retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, max=15),
    retry=retry_if_exception(_is_retryable),
)


class AnthropicService:
    """Anthropic Claude service wrapper (async SDK client)."""

    def __init__(
        self,
        api_key: str | None = None,
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
            str: Assistant response text

        Raises:
            LLMServiceError: If the API fails after retries
        """
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        chat_messages = [m for m in messages if m.get("role") != "system"]
        if not chat_messages:
            chat_messages = [{"role": "user", "content": " "}]

        try:
            response = await self._create_message(system_parts, chat_messages)
        except Exception as e:
            logger.error(f"Anthropic chat error: {e}")
            raise LLMServiceError(f"Anthropic chat failed: {e}") from e

        if response.stop_reason == "refusal":
            logger.warning("Anthropic request was refused by safety classifiers")
            return ""
        return "".join(block.text for block in response.content if block.type == "text")

    @anthropic_retry
    async def _create_message(self, system_parts: list[str], chat_messages: list[dict[str, str]]):
        return await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system="\n\n".join(system_parts) or anthropic.NOT_GIVEN,
            messages=chat_messages,
            thinking={"type": "adaptive"},
        )

    async def generate(self, prompt: str, system: str | None = None) -> str:
        """Generate text from a plain prompt (OllamaService-compatible)."""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return await self.chat(messages)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self.client.close()
