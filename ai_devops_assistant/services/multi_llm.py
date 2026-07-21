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

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

import aiohttp

from ai_devops_assistant.observability.ai_observability import LLMTrace

logger = logging.getLogger(__name__)


class LLMProviderError(RuntimeError):
    """A provider could not produce a response.

    Providers raise this instead of returning "". An empty string is
    indistinguishable from a model that legitimately produced no text, so
    failures used to surface as a blank assistant message rather than an error —
    silent in the logs and confusing in the UI.
    """


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    Messages-first, not prompt-first. Anthropic and OpenAI are natively
    messages-based, and flattening a conversation into one string destroys the
    system/user boundary — which is precisely the boundary that keeps retrieved
    documents and tool output from being read as instructions. A prompt-string
    interface would make prompt-injection defence impossible to express, so
    ``chat`` and ``stream_chat`` are the primitives and the single-prompt forms
    are conveniences built on top.

    Subclasses implement ``chat`` and ``stream_chat``; ``generate`` and
    ``stream_generate`` are inherited unless a provider can do better.
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> str:
        """Generate a reply to a conversation.

        Args:
            messages: [{"role": "system"|"user"|"assistant", "content": str}, ...]
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0-2)
            **kwargs: Provider-specific parameters

        Returns:
            Generated text
        """

    @abstractmethod
    def stream_chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream a reply to a conversation.

        Not `async def`: implementations are async generators, so calling this
        returns the iterator directly rather than a coroutine wrapping one.

        Args:
            messages: Conversation messages
            max_tokens: Maximum tokens
            temperature: Sampling temperature
            **kwargs: Provider-specific parameters

        Yields:
            Text chunks as they are generated
        """

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 0.9,
        **kwargs: Any,
    ) -> str:
        """Generate text from a single prompt.

        Convenience wrapper over chat(); a bare prompt is one user message.
        """
        return await self.chat(
            [{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            **kwargs,
        )

    def stream_generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream text from a single prompt.

        Convenience wrapper over stream_chat().
        """
        return self.stream_chat(
            [{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

    async def health_check(self) -> bool:
        """Whether the provider is reachable.

        The default asks the model for one token, which works for any provider
        but costs a request; providers with a cheap liveness endpoint should
        override it.
        """
        try:
            await self.chat([{"role": "user", "content": "ping"}], max_tokens=1)
            return True
        except Exception as e:
            logger.warning(f"{type(self).__name__} health check failed: {e}")
            return False

    async def close(self) -> None:
        """Release any held resources. No-op unless a provider needs it."""
        return None


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

    async def health_check(self) -> bool:
        """Cheap liveness check: Ollama's tag listing needs no inference."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return bool(resp.status == 200)
        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")
            return False

    async def list_models(self) -> list[str]:
        """Model names available on this Ollama server (for the model picker)."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    return [m["name"] for m in data.get("models", []) if "name" in m]
        except Exception as e:
            logger.warning(f"Could not list Ollama models: {e}")
            return []

    async def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> str:
        """Generate a reply using Ollama's /api/chat.

        Uses the chat endpoint rather than /api/generate so the system/user roles
        survive to the model instead of being flattened into one string.

        Args:
            messages: Conversation messages
            max_tokens: Maximum tokens
            temperature: Sampling temperature
            **kwargs: top_p and other Ollama options

        Returns:
            Generated text

        Raises:
            LLMProviderError: If the request fails.
        """
        payload = {
            # A caller may override the model per request (the UI's model
            # picker does); fall back to the one this provider was built with.
            "model": kwargs.get("model") or self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": kwargs.get("top_p", 0.9),
                "num_predict": max_tokens,
            },
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise LLMProviderError(f"Ollama returned {resp.status}: {body[:200]}")
                    data = await resp.json()
                    return str(data.get("message", {}).get("content", ""))
        except LLMProviderError:
            raise
        except Exception as e:
            # Raise rather than return "": an empty string is indistinguishable
            # from a model that legitimately said nothing, and it silently
            # becomes an empty reply in the UI.
            raise LLMProviderError(f"Ollama request failed: {e}") from e

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream a reply from Ollama.

        Args:
            messages: Conversation messages
            max_tokens: Maximum tokens
            temperature: Sampling temperature
            **kwargs: Provider-specific parameters

        Yields:
            Text chunks

        Raises:
            LLMProviderError: If the request fails before any chunk arrives.
        """
        payload = {
            # A caller may override the model per request (the UI's model
            # picker does); fall back to the one this provider was built with.
            "model": kwargs.get("model") or self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise LLMProviderError(f"Ollama returned {resp.status}: {body[:200]}")

                    async for line in resp.content:
                        if not line:
                            continue
                        try:
                            data = json.loads(line.decode())
                        except json.JSONDecodeError:
                            # Ollama emits one JSON object per line; a partial
                            # line is not fatal, the next read completes it.
                            continue
                        chunk = data.get("message", {}).get("content", "")
                        if chunk:
                            yield chunk
        except LLMProviderError:
            raise
        except Exception as e:
            raise LLMProviderError(f"Ollama streaming failed: {e}") from e


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

    async def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> str:
        """Generate a reply using OpenAI chat completions.

        OpenAI is natively messages-based, so the conversation passes straight
        through — no flattening, and the system role is preserved.

        Raises:
            LLMProviderError: If the request fails.
        """
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            # A caller may override the model per request (the UI's model
            # picker does); fall back to the one this provider was built with.
            "model": kwargs.get("model") or self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": kwargs.get("top_p", 0.9),
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        raise LLMProviderError(f"OpenAI returned {resp.status}: {error[:200]}")
                    data = await resp.json()
                    return str(data["choices"][0]["message"]["content"])
        except LLMProviderError:
            raise
        except Exception as e:
            raise LLMProviderError(f"OpenAI request failed: {e}") from e

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream a reply from OpenAI.

        Yields:
            Text chunks

        Raises:
            LLMProviderError: If the request fails before any chunk arrives.
        """
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            # A caller may override the model per request (the UI's model
            # picker does); fall back to the one this provider was built with.
            "model": kwargs.get("model") or self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        raise LLMProviderError(f"OpenAI returned {resp.status}: {error[:200]}")

                    async for line in resp.content:
                        if not line:
                            continue
                        line_str = line.decode().strip()
                        if not line_str.startswith("data: "):
                            continue
                        payload_str = line_str[6:]
                        if payload_str == "[DONE]":
                            break
                        try:
                            data = json.loads(payload_str)
                        except json.JSONDecodeError:
                            continue
                        content = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if content:
                            yield content
        except LLMProviderError:
            raise
        except Exception as e:
            raise LLMProviderError(f"OpenAI streaming failed: {e}") from e


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

    @staticmethod
    def _split_system(messages: list[dict[str, str]]) -> tuple[str | None, list[dict[str, str]]]:
        """Separate system messages from the conversation.

        Anthropic takes the system prompt as its own top-level parameter, not as
        a message with role "system" — passing one in the messages array is a
        request error. Multiple system messages are joined, preserving order.
        """
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        conversation = [m for m in messages if m.get("role") != "system"]
        return ("\n\n".join(system_parts) or None), conversation

    async def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> str:
        """Generate a reply using Anthropic Claude.

        Note: temperature/top_p are accepted for interface compatibility but not
        sent — sampling parameters are rejected by current Claude models.

        Raises:
            LLMProviderError: If the request fails or is refused.
        """
        system, conversation = self._split_system(messages)
        request: dict[str, Any] = {
            # A caller may override the model per request (the UI's model
            # picker does); fall back to the one this provider was built with.
            "model": kwargs.get("model") or self.model,
            "max_tokens": max_tokens,
            "messages": conversation,
            "thinking": {"type": "adaptive"},
        }
        if system:
            request["system"] = system

        try:
            response = await self.client.messages.create(**request)
        except Exception as e:
            raise LLMProviderError(f"Anthropic request failed: {e}") from e

        if response.stop_reason == "refusal":
            # A refusal is a real outcome, not an empty answer; surfacing it as
            # "" made it indistinguishable from a successful empty reply.
            raise LLMProviderError("Anthropic refused the request")

        return "".join(b.text for b in response.content if b.type == "text")

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream a reply from Anthropic.

        Yields:
            Text chunks

        Raises:
            LLMProviderError: If the request fails before any chunk arrives.
        """
        system, conversation = self._split_system(messages)
        request: dict[str, Any] = {
            # A caller may override the model per request (the UI's model
            # picker does); fall back to the one this provider was built with.
            "model": kwargs.get("model") or self.model,
            "max_tokens": max_tokens,
            "messages": conversation,
            "thinking": {"type": "adaptive"},
        }
        if system:
            request["system"] = system

        try:
            async with self.client.messages.stream(**request) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as e:
            raise LLMProviderError(f"Anthropic streaming failed: {e}") from e


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


class FallbackLLMClient(LLMProvider):
    """Tries multiple model targets in order, using the first that answers.

    Implements LLMProvider itself, so it is substitutable anywhere a single
    provider is — including as the agent's LLM.
    """

    def __init__(self, targets: list[dict]):
        self.targets = targets

    def _plan(self, kwargs: dict) -> list[dict]:
        """Targets to try, honouring an explicit per-request model.

        Removes ``model`` from kwargs: this class picks the model per target, and
        leaving it in would forward the same model to every provider below,
        turning a fallback chain into the same failing call repeated.

        An explicitly requested model is tried first and the configured chain
        still follows it, so choosing a model does not cost the caller the
        fallback safety net.
        """
        requested = kwargs.pop("model", None)
        if not requested or not self.targets:
            return self.targets
        rest = [t for t in self.targets if t.get("model") != requested]
        return [{"provider": self.targets[0]["provider"], "model": requested}, *rest]

    async def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> str:
        """Try each target in order and return the first successful reply.

        Raises:
            LLMProviderError: If every target fails. This used to return "",
                which reached the UI as an empty assistant message with nothing
                in the logs to explain it — a total outage that looked like the
                model simply had nothing to say.
        """
        last_error = "no targets configured"

        for target in self._plan(kwargs):
            provider = target["provider"]
            model = target["model"]
            llm = LLMFactory.create(provider, model=model, **target.get("kwargs", {}))
            if llm is None:
                last_error = f"could not construct provider {provider}"
                continue

            trace = LLMTrace(provider=provider, model=model, prompt=_trace_prompt(messages))
            try:
                response = await llm.chat(
                    messages, max_tokens=max_tokens, temperature=temperature, **kwargs
                )
            except Exception as exc:
                last_error = str(exc)
                trace.complete(response="", error=last_error)
                logger.warning(f"Fallback target failed {provider}/{model}: {exc}")
                continue

            if response:
                trace.complete(response=response)
                return response

            # An empty but successful reply still counts as a failure for
            # fallback purposes: try the next target rather than return nothing.
            last_error = f"{provider}/{model} returned an empty response"
            trace.complete(response="", error=last_error)

        logger.error(f"All fallback models failed: {last_error}")
        raise LLMProviderError(f"All LLM targets failed. Last error: {last_error}")

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream from the first target that starts producing output.

        A target is considered good once its first chunk arrives; a failure after
        that is not retried, because the consumer has already seen partial
        output and replaying it from another model would corrupt the response.

        Raises:
            LLMProviderError: If no target produces any output.
        """
        last_error = "no targets configured"

        for target in self._plan(kwargs):
            provider = target["provider"]
            model = target["model"]
            llm = LLMFactory.create(provider, model=model, **target.get("kwargs", {}))
            if llm is None:
                last_error = f"could not construct provider {provider}"
                continue

            started = False
            try:
                async for chunk in llm.stream_chat(
                    messages, max_tokens=max_tokens, temperature=temperature, **kwargs
                ):
                    started = True
                    yield chunk
            except Exception as exc:
                last_error = str(exc)
                logger.warning(f"Fallback stream failed {provider}/{model}: {exc}")
                if started:
                    # Mid-stream failure: the caller already has part of this
                    # answer, so switching models would splice two replies.
                    raise LLMProviderError(
                        f"Stream from {provider}/{model} failed after partial output: {exc}"
                    ) from exc
                continue

            if started:
                return

            last_error = f"{provider}/{model} produced no output"

        raise LLMProviderError(f"All LLM targets failed. Last error: {last_error}")


def _trace_prompt(messages: list[dict[str, str]]) -> str:
    """Flatten messages for the observability trace only, never for a request."""
    return "\n".join(f"{m.get('role', '?')}: {m.get('content', '')}" for m in messages)
