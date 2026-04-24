"""LLM Model Registry Integration.

This module provides interfaces to discover and download LLM models from various registries.
Supported registries:
- Hugging Face Hub: Access to thousands of open-source models
- Ollama Registry: Local model management for Ollama

Example:
    >>> from ai_devops_assistant.services.model_registry import ModelRegistry
    >>> registry = ModelRegistry()
    >>> models = registry.search_models("llama")
    >>> model_info = registry.get_model_info("meta-llama/Llama-2-7b")
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Optional

import aiohttp
import requests

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """Model information from registry."""

    name: str
    id: str
    description: str
    size_gb: Optional[float]
    parameters: Optional[str]
    license: str
    tags: list[str]
    downloads: Optional[int]
    rating: Optional[float]
    url: str


class ModelRegistry:
    """Base class for LLM model registries."""

    async def search_models(self, query: str, limit: int = 20) -> list[ModelInfo]:
        """Search for models in the registry.

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of ModelInfo objects
        """
        raise NotImplementedError

    async def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        """Get detailed information about a specific model.

        Args:
            model_id: Model identifier

        Returns:
            ModelInfo object or None if not found
        """
        raise NotImplementedError

    async def download_model(
        self, model_id: str, destination: str, progress_callback=None
    ) -> bool:
        """Download a model to local storage.

        Args:
            model_id: Model identifier
            destination: Local destination path
            progress_callback: Optional callback for progress updates

        Returns:
            True if successful, False otherwise
        """
        raise NotImplementedError


class HuggingFaceRegistry(ModelRegistry):
    """Hugging Face Hub model registry integration."""

    BASE_URL = "https://huggingface.co/api"
    MODELS_ENDPOINT = "/models"

    def __init__(self, api_key: Optional[str] = None):
        """Initialize HuggingFace registry.

        Args:
            api_key: Optional HuggingFace API key
        """
        self.api_key = api_key
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def search_models(
        self, query: str, limit: int = 20, model_type: str = "text-generation"
    ) -> list[ModelInfo]:
        """Search HuggingFace models.

        Args:
            query: Search query
            limit: Maximum results
            model_type: Type of model to search (text-generation, language-model, etc.)

        Returns:
            List of ModelInfo objects
        """
        try:
            session = await self._get_session()
            params = {
                "search": query,
                "limit": limit,
                "task": model_type,
                "sort": "downloads",
            }

            async with session.get(
                f"{self.BASE_URL}{self.MODELS_ENDPOINT}", params=params
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return [self._parse_model(model) for model in data]

            logger.error(f"Failed to search models: {resp.status}")
            return []

        except Exception as e:
            logger.error(f"Error searching HuggingFace models: {e}")
            return []

    async def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        """Get HuggingFace model information.

        Args:
            model_id: Model identifier (e.g., 'meta-llama/Llama-2-7b')

        Returns:
            ModelInfo object or None
        """
        try:
            session = await self._get_session()

            async with session.get(
                f"{self.BASE_URL}{self.MODELS_ENDPOINT}/{model_id}"
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return self._parse_model(data)

            return None

        except Exception as e:
            logger.error(f"Error getting model info: {e}")
            return None

    def _parse_model(self, model_data: dict) -> ModelInfo:
        """Parse HuggingFace model data to ModelInfo."""
        return ModelInfo(
            name=model_data.get("modelId", ""),
            id=model_data.get("modelId", ""),
            description=model_data.get("description", ""),
            size_gb=None,  # Not provided by HF API
            parameters=model_data.get("tags", {}).get("model_architecture"),
            license=model_data.get("modelId", "").split("/")[0],
            tags=model_data.get("tags", []),
            downloads=model_data.get("downloads", 0),
            rating=model_data.get("rating"),
            url=f"https://huggingface.co/{model_data.get('modelId')}",
        )

    async def close(self):
        """Clean up session."""
        if self.session:
            await self.session.close()


class OllamaRegistry(ModelRegistry):
    """Ollama local model registry integration."""

    def __init__(self, base_url: str = "http://localhost:11434"):
        """Initialize Ollama registry.

        Args:
            base_url: Ollama server base URL
        """
        self.base_url = base_url

    def search_models(self, query: str, limit: int = 20) -> list[ModelInfo]:
        """Search Ollama models.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of available models
        """
        try:
            # Ollama doesn't have a built-in search, return available models
            resp = requests.get(f"{self.base_url}/api/tags", timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                models = data.get("models", [])

                # Filter by query
                filtered = [
                    m for m in models if query.lower() in m.get("name", "").lower()
                ][:limit]

                return [
                    ModelInfo(
                        name=m.get("name", ""),
                        id=m.get("name", ""),
                        description=f"Ollama model: {m.get('name', '')}",
                        size_gb=m.get("size", 0) / (1024**3),  # Convert bytes to GB
                        parameters=None,
                        license="Various",
                        tags=[],
                        downloads=None,
                        rating=None,
                        url="",
                    )
                    for m in filtered
                ]

            return []

        except Exception as e:
            logger.error(f"Error searching Ollama models: {e}")
            return []

    def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        """Get Ollama model information.

        Args:
            model_id: Model name

        Returns:
            ModelInfo or None
        """
        try:
            models = self.search_models(model_id, limit=1)
            return models[0] if models else None
        except Exception as e:
            logger.error(f"Error getting Ollama model info: {e}")
            return None

    def download_model(
        self, model_id: str, destination: str = None, progress_callback=None
    ) -> bool:
        """Pull/download an Ollama model.

        Args:
            model_id: Model name
            destination: Ignored for Ollama (manages its own storage)
            progress_callback: Optional callback for progress

        Returns:
            True if successful
        """
        try:
            resp = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": model_id},
                timeout=3600,  # Long timeout for download
                stream=True,
            )

            if resp.status_code == 200:
                for line in resp.iter_lines():
                    if line and progress_callback:
                        try:
                            data = json.loads(line)
                            progress_callback(data)
                        except json.JSONDecodeError:
                            pass

                logger.info(f"Successfully pulled model: {model_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error pulling Ollama model: {e}")
            return False


class CompositeRegistry(ModelRegistry):
    """Composite registry that searches multiple sources."""

    def __init__(self):
        """Initialize with multiple registries."""
        self.registries = {
            "huggingface": HuggingFaceRegistry(),
            "ollama": OllamaRegistry(),
        }

    async def search_models(self, query: str, limit: int = 20) -> list[ModelInfo]:
        """Search across all registries.

        Args:
            query: Search query
            limit: Maximum results per registry

        Returns:
            Combined list of models
        """
        results = []

        # Search HuggingFace
        try:
            hf_results = await self.registries["huggingface"].search_models(
                query, limit
            )
            results.extend(hf_results)
        except Exception as e:
            logger.warning(f"HuggingFace search failed: {e}")

        # Search Ollama
        try:
            ollama_results = self.registries["ollama"].search_models(query, limit)
            results.extend(ollama_results)
        except Exception as e:
            logger.warning(f"Ollama search failed: {e}")

        return results[:limit]

    async def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        """Get model info from appropriate registry.

        Args:
            model_id: Model identifier

        Returns:
            ModelInfo or None
        """
        # Try Ollama first (local)
        try:
            info = self.registries["ollama"].get_model_info(model_id)
            if info:
                return info
        except Exception as e:
            logger.debug(f"Ollama lookup failed: {e}")

        # Try HuggingFace
        try:
            info = await self.registries["huggingface"].get_model_info(model_id)
            if info:
                return info
        except Exception as e:
            logger.debug(f"HuggingFace lookup failed: {e}")

        return None
