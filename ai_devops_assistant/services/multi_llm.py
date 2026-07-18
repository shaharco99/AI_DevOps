"""Multi-LLM Support Abstraction Layer.

Provides a unified interface to multiple LLM providers:
- Ollama (local)
- OpenAI (cloud)
- Anthropic (cloud)
- HuggingFace Transformers (local/cloud)

Example:
    >>> from ai_devops_assistant.services.multi_llm import LLMFactory
    >>> llm = LLMFactory.create("openai", api_key="sk-...")
    >>> response = await llm.generate("Analyze this log")
"""

import logging
from abc import ABC, abstractmethod

import aiohttp

from ai_devops_assistant.observability.ai_observability import LLMTrace

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        """Generate text from prompt.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0-2)
            top_p: Nucleus sampling parameter

        Returns:
            Generated text
        """
        pass

    @abstractmethod
    async def stream_generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ):
        """Generate text with streaming.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens
            temperature: Sampling temperature

        Yields:
            Text chunks as they are generated
        """
        pass


class OllamaProvider(LLMProvider):
    """Ollama LLM provider for local models."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3",
        timeout: int = 60,
    ):
        """Initialize Ollama provider.

        Args:
            base_url: Ollama server URL
            model: Model name
            timeout: Request timeout in seconds
        """
        self.base_url = base_url
        self.model = model
        self.timeout = timeout

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        """Generate using Ollama.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens
            temperature: Sampling temperature
            top_p: Nucleus sampling

        Returns:
            Generated text
        """
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "temperature": temperature,
                "top_p": top_p,
                "num_predict": max_tokens,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return str(data.get("response", ""))

                    logger.error(f"Ollama error: {resp.status}")
                    return ""

        except Exception as e:
            logger.error(f"Ollama generation error: {e}")
            return ""

    async def stream_generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ):
        """Stream generation from Ollama.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens
            temperature: Sampling temperature

        Yields:
            Text chunks
        """
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": True,
                "temperature": temperature,
                "num_predict": max_tokens,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status == 200:
                        async for line in resp.content:
                            if line:
                                import json

                                try:
                                    data = json.loads(line.decode())
                                    yield data.get("response", "")
                                except json.JSONDecodeError:
                                    pass

        except Exception as e:
            logger.error(f"Ollama streaming error: {e}")


class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider."""

    def __init__(self, api_key: str, model: str = "gpt-4", timeout: int = 60):
        """Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key
            model: Model name
            timeout: Request timeout
        """
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.base_url = "https://api.openai.com/v1"

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        """Generate using OpenAI.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens
            temperature: Sampling temperature
            top_p: Nucleus sampling

        Returns:
            Generated text
        """
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return str(data["choices"][0]["message"]["content"])

                    error = await resp.text()
                    logger.error(f"OpenAI error: {resp.status} - {error}")
                    return ""

        except Exception as e:
            logger.error(f"OpenAI generation error: {e}")
            return ""

    async def stream_generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ):
        """Stream generation from OpenAI.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens
            temperature: Sampling temperature

        Yields:
            Text chunks
        """
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status == 200:
                        async for line in resp.content:
                            if line:
                                line_str = line.decode().strip()
                                if line_str.startswith("data: "):
                                    import json

                                    try:
                                        data = json.loads(line_str[6:])
                                        delta = data.get("choices", [{}])[0].get("delta", {})
                                        content = delta.get("content", "")
                                        if content:
                                            yield content
                                    except json.JSONDecodeError:
                                        pass

        except Exception as e:
            logger.error(f"OpenAI streaming error: {e}")


class AnthropicProvider(LLMProvider):
    """Anthropic Claude LLM provider (official SDK)."""

    def __init__(self, api_key: str | None = None, model: str = "claude-opus-4-8"):
        """Initialize Anthropic provider.

        Args:
            api_key: Anthropic API key (falls back to environment credentials)
            model: Model ID
        """
        import anthropic

        self.model = model
        if api_key:
            self.client = anthropic.AsyncAnthropic(api_key=api_key)
        else:
            self.client = anthropic.AsyncAnthropic()

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        """Generate using Anthropic Claude.

        Note: temperature/top_p are accepted for interface compatibility but not
        sent — sampling parameters are rejected by current Claude models.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens

        Returns:
            Generated text
        """
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                thinking={"type": "adaptive"},
            )
            if response.stop_reason == "refusal":
                logger.warning("Anthropic request refused by safety classifiers")
                return ""
            return "".join(b.text for b in response.content if b.type == "text")
        except Exception as e:
            logger.error(f"Anthropic generation error: {e}")
            return ""

    async def stream_generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ):
        """Stream generation from Anthropic.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens

        Yields:
            Text chunks
        """
        try:
            async with self.client.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                thinking={"type": "adaptive"},
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as e:
            logger.error(f"Anthropic streaming error: {e}")


class LLMFactory:
    """Factory for creating LLM provider instances."""

    _providers: dict[str, type[LLMProvider]] = {
        "ollama": OllamaProvider,
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
    }

    @classmethod
    def create(cls, provider_name: str, **kwargs) -> LLMProvider | None:
        """Create an LLM provider instance.

        Args:
            provider_name: Name of the provider (ollama, openai, anthropic)
            **kwargs: Provider-specific arguments

        Returns:
            LLMProvider instance or None if provider not found
        """
        provider_class = cls._providers.get(provider_name.lower())

        if not provider_class:
            logger.error(f"Unknown provider: {provider_name}")
            return None

        try:
            return provider_class(**kwargs)
        except Exception as e:
            logger.error(f"Error creating {provider_name} provider: {e}")
            return None

    @classmethod
    def get_available_providers(cls) -> list[str]:
        """Get list of available providers.

        Returns:
            List of provider names
        """
        return list(cls._providers.keys())


class FallbackLLMClient:
    """Fallback client that tries multiple model targets in order."""

    def __init__(self, targets: list[dict]):
        self.targets = targets

    async def generate(self, prompt: str, **kwargs) -> str:
        last_error = None
        for target in self.targets:
            provider = target["provider"]
            model = target["model"]
            provider_kwargs = target.get("kwargs", {})
            llm = LLMFactory.create(provider, model=model, **provider_kwargs)
            if llm is None:
                continue

            trace = LLMTrace(provider=provider, model=model, prompt=prompt)
            try:
                response = await llm.generate(prompt, **kwargs)
                if response:
                    trace.complete(response=response)
                    return response
            except Exception as exc:
                last_error = str(exc)
                trace.complete(response="", error=last_error)
                logger.warning(f"Fallback target failed {provider}/{model}: {exc}")

        logger.error(f"All fallback models failed: {last_error}")
        return ""
