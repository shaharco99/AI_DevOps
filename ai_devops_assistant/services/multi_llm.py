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

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional

import aiohttp
import requests

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
                        return data.get("response", "")

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
                        return data["choices"][0]["message"]["content"]

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
                                        delta = data.get("choices", [{}])[0].get(
                                            "delta", {}
                                        )
                                        content = delta.get("content", "")
                                        if content:
                                            yield content
                                    except json.JSONDecodeError:
                                        pass

        except Exception as e:
            logger.error(f"OpenAI streaming error: {e}")


class AnthropicProvider(LLMProvider):
    """Anthropic Claude LLM provider."""

    def __init__(self, api_key: str, model: str = "claude-3-sonnet-20240229"):
        """Initialize Anthropic provider.

        Args:
            api_key: Anthropic API key
            model: Model name
        """
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.anthropic.com/v1"

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        """Generate using Anthropic Claude.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens
            temperature: Sampling temperature
            top_p: Nucleus sampling

        Returns:
            Generated text
        """
        try:
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            }
            payload = {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "top_p": top_p,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/messages", json=payload, headers=headers
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["content"][0]["text"]

                    error = await resp.text()
                    logger.error(f"Anthropic error: {resp.status} - {error}")
                    return ""

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
            temperature: Sampling temperature

        Yields:
            Text chunks
        """
        try:
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            }
            payload = {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "stream": True,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/messages", json=payload, headers=headers
                ) as resp:
                    if resp.status == 200:
                        async for line in resp.content:
                            if line:
                                line_str = line.decode().strip()
                                if line_str.startswith("data: "):
                                    import json

                                    try:
                                        data = json.loads(line_str[6:])
                                        if (
                                            data.get("type")
                                            == "content_block_delta"
                                        ):
                                            delta = data.get("delta", {})
                                            text = delta.get("text", "")
                                            if text:
                                                yield text
                                    except json.JSONDecodeError:
                                        pass

        except Exception as e:
            logger.error(f"Anthropic streaming error: {e}")


class LLMFactory:
    """Factory for creating LLM provider instances."""

    _providers = {
        "ollama": OllamaProvider,
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
    }

    @classmethod
    def create(cls, provider_name: str, **kwargs) -> Optional[LLMProvider]:
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
