"""Ollama LLM service integration."""

import asyncio
import json
import logging
from typing import Any, Optional

import httpx

from ai_devops_assistant.config.settings import settings

logger = logging.getLogger(__name__)


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

    async def health_check(self) -> bool:
        """Check if Ollama is healthy.
        
        Returns:
            bool: True if healthy, False otherwise
        """
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
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
        system: Optional[str] = None,
    ) -> str:
        """Generate text from prompt.
        
        Args:
            prompt: Input prompt
            system: Optional system prompt
            
        Returns:
            str: Generated text
        """
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "temperature": self.temperature,
                "stream": False,
            }
            
            if system:
                payload["system"] = system

            response = await self.client.post(
                f"{self.base_url}/api/generate",
                json=payload,
            )
            
            if response.status_code == 200:
                data = response.json()
                generated_text = data.get("response", "")
                logger.debug(f"Generated {len(generated_text)} characters")
                return generated_text
            else:
                logger.error(f"Generation failed: {response.status_code}")
                return ""
                
        except Exception as e:
            logger.error(f"Generation error: {e}")
            return ""

    async def chat(
        self,
        messages: list[dict[str, str]],
    ) -> str:
        """Chat with model.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            
        Returns:
            str: Assistant response
        """
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "stream": False,
            }

            response = await self.client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            
            if response.status_code == 200:
                data = response.json()
                assistant_message = data.get("message", {}).get("content", "")
                return assistant_message
            else:
                logger.error(f"Chat failed: {response.status_code}")
                return ""
                
        except Exception as e:
            logger.error(f"Chat error: {e}")
            return ""

    async def stream_generate(
        self,
        prompt: str,
        system: Optional[str] = None,
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
        model: Optional[str] = None,
    ) -> Optional[list[float]]:
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
                return data.get("embedding")
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
_ollama_service: Optional[OllamaService] = None


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
