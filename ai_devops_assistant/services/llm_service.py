"""Ollama LLM service integration."""

import json
import logging
from typing import cast

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from ai_devops_assistant.config.settings import settings

logger = logging.getLogger(__name__)


class LLMServiceError(Exception):
    """Raised when an LLM backend call fails after retries.

    Lets callers distinguish "backend down/errored" from "model returned
    an empty answer".
    """


def _is_retryable(exc: BaseException) -> bool:
    """Retry on transport failures and 5xx responses, not on 4xx."""
    if isinstance(exc, httpx.TransportError):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500


llm_retry = retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=8),
    retry=retry_if_exception(_is_retryable),
)


class OllamaService:
    """Ollama LLM service wrapper."""

    def __init__(
        self,
        base_url: str = settings.OLLAMA_BASE_URL,
        model: str = settings.LLM_MODEL,
        temperature: float = settings.LLM_TEMPERATURE,
        max_tokens: int = settings.LLM_MAX_TOKENS,
        timeout: int = settings.LLM_TIMEOUT,
    ):
        """Initialize Ollama service.

        Args:
            base_url: Ollama base URL
            model: Model name to use
            temperature: Temperature for generation
            max_tokens: Max tokens to generate
            timeout: Request timeout
        """
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    @llm_retry
    async def _post(self, path: str, payload: dict) -> httpx.Response:
        """POST with retry on transient failures (transport errors, 5xx)."""
        response = await self.client.post(f"{self.base_url}{path}", json=payload)
        response.raise_for_status()
        return response

    async def health_check(self) -> bool:
        """Check if Ollama is healthy.

        Returns:
            bool: True if healthy, False otherwise
        """
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            return bool(response.status_code == 200)
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False

    async def list_models(self) -> list[str]:
        """List available models.

        Returns:
            list: Model names
        """
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                return [m.get("name") for m in models if m.get("name")]
            return []
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            return []

    async def pull_model(self, model: str) -> bool:
        """Pull a model from Ollama registry.

        Args:
            model: Model name to pull

        Returns:
            bool: True if successful
        """
        try:
            logger.info(f"Pulling model: {model}")
            response = await self.client.post(
                f"{self.base_url}/api/pull",
                json={"name": model},
            )
            if response.status_code == 200:
                logger.info(f"Model {model} pulled successfully")
                return True
            else:
                logger.error(f"Failed to pull model {model}: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Error pulling model {model}: {e}")
            return False

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
    ) -> str:
        """Generate text from prompt.

        Args:
            prompt: Input prompt
            system: Optional system prompt

        Returns:
            str: Generated text

        Raises:
            LLMServiceError: If the backend fails after retries
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "temperature": self.temperature,
            "stream": False,
        }

        if system:
            payload["system"] = system

        try:
            response = await self._post("/api/generate", payload)
        except Exception as e:
            logger.error(f"Generation error: {e}")
            raise LLMServiceError(f"Ollama generate failed: {e}") from e

        generated_text = str(response.json().get("response", ""))
        logger.debug(f"Generated {len(generated_text)} characters")
        return generated_text

    async def chat(
        self,
        messages: list[dict[str, str]],
    ) -> str:
        """Chat with model.

        Args:
            messages: List of message dicts with 'role' and 'content'

        Returns:
            str: Assistant response

        Raises:
            LLMServiceError: If the backend fails after retries
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": False,
        }

        try:
            response = await self._post("/api/chat", payload)
        except Exception as e:
            logger.error(f"Chat error: {e}")
            raise LLMServiceError(f"Ollama chat failed: {e}") from e

        return str(response.json().get("message", {}).get("content", ""))

    async def stream_generate(
        self,
        prompt: str,
        system: str | None = None,
    ):
        """Generate text with streaming.

        Args:
            prompt: Input prompt
            system: Optional system prompt

        Yields:
            str: Generated text chunks
        """
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "temperature": self.temperature,
                "stream": True,
            }

            if system:
                payload["system"] = system

            async with self.client.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json=payload,
            ) as response:
                if response.status_code == 200:
                    async for line in response.aiter_lines():
                        if line:
                            data = json.loads(line)
                            chunk = data.get("response", "")
                            if chunk:
                                yield chunk
                else:
                    logger.error(f"Stream generation failed: {response.status_code}")

        except Exception as e:
            logger.error(f"Stream generation error: {e}")

    async def embeddings(
        self,
        text: str,
        model: str | None = None,
    ) -> list[float] | None:
        """Generate embeddings for text.

        Args:
            text: Text to embed
            model: Optional model (uses default if not specified)

        Returns:
            list: Embedding vector or None
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/api/embeddings",
                json={
                    "model": model or self.model,
                    "prompt": text,
                },
            )

            if response.status_code == 200:
                data = response.json()
                return cast("list[float] | None", data.get("embedding"))
            else:
                logger.error(f"Embeddings failed: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Embeddings error: {e}")
            return None

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Global service instance
_ollama_service: OllamaService | None = None


async def get_ollama_service() -> OllamaService:
    """Get or create Ollama service instance.

    Returns:
        OllamaService: Ollama service instance
    """
    global _ollama_service
    if _ollama_service is None:
        _ollama_service = OllamaService()
        # Check health
        if not await _ollama_service.health_check():
            logger.warning("Ollama service not reachable")
    return _ollama_service


async def close_ollama_service() -> None:
    """Close Ollama service."""
    global _ollama_service
    if _ollama_service:
        await _ollama_service.close()
        _ollama_service = None


# Provider-agnostic accessors — selected via settings.LLM_PROVIDER
_anthropic_service = None


async def get_llm_service():
    """Get the LLM service for the configured provider.

    Returns:
        OllamaService or AnthropicService (same chat/generate/health_check interface)
    """
    global _anthropic_service
    provider = settings.LLM_PROVIDER.lower()

    if provider == "anthropic":
        if _anthropic_service is None:
            from ai_devops_assistant.services.anthropic_service import AnthropicService

            _anthropic_service = AnthropicService()
            if not await _anthropic_service.health_check():
                logger.warning("Anthropic service not reachable")
        return _anthropic_service

    if provider != "ollama":
        logger.warning(f"Unknown LLM_PROVIDER '{provider}', falling back to ollama")
    return await get_ollama_service()


async def close_llm_service() -> None:
    """Close whichever LLM services were created."""
    global _anthropic_service
    if _anthropic_service:
        await _anthropic_service.close()
        _anthropic_service = None
    await close_ollama_service()
