"""Embeddings initialization and management."""

import logging
from typing import Any, Optional

import ollama

from ai_devops_assistant.config.settings import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Embedding model service."""

    def __init__(self, model_name: str = settings.EMBEDDING_MODEL):
        """Initialize embedding service.
        
        Args:
            model_name: HuggingFace model name
        """
        self.model_name = model_name
        self.model: Optional[str] = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the embedding model."""
        if self._initialized:
            return

        try:
            logger.info(f"Initializing embedding model: {self.model_name}")
            self.model = self.model_name
            self._initialized = True
            logger.info("Embedding model initialized successfully")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise

    def embed(self, text: str) -> list[float]:
        """Generate embedding for text.
        
        Args:
            text: Text to embed
            
        Returns:
            list: Embedding vector
            
        Raises:
            ValueError: If model not initialized
        """
        if not self._initialized or self.model is None:
            raise ValueError("Embedding model not initialized. Call initialize() first.")

        try:
            response: Any
            try:
                response = ollama.embed(model=self.model_name, input=text)
                return response["embeddings"][0]
            except Exception:
                response = ollama.embeddings(model=self.model_name, prompt=text)
                return response["embedding"]
        except Exception as e:
            logger.error(f"Failed to embed text: {e}")
            raise

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.
        
        Args:
            texts: Texts to embed
            
        Returns:
            list: List of embedding vectors
            
        Raises:
            ValueError: If model not initialized
        """
        if not self._initialized or self.model is None:
            raise ValueError("Embedding model not initialized. Call initialize() first.")

        try:
            response: Any
            try:
                response = ollama.embed(model=self.model_name, input=texts)
                return response["embeddings"]
            except Exception:
                return [self.embed(text) for text in texts]
        except Exception as e:
            logger.error(f"Failed to embed texts: {e}")
            raise

    def get_dimension(self) -> int:
        """Get embedding dimension.
        
        Returns:
            int: Embedding dimension
            
        Raises:
            ValueError: If model not initialized
        """
        if not self._initialized or self.model is None:
            raise ValueError("Embedding model not initialized.")
        return len(self.embed("dimension-probe"))


# Global instance
_embedding_service: Optional[EmbeddingService] = None


async def get_embedding_service() -> EmbeddingService:
    """Get or create embedding service.
    
    Returns:
        EmbeddingService: Embedding service instance
    """
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
        await _embedding_service.initialize()
    return _embedding_service


def get_embedding_service_sync() -> EmbeddingService:
    """Get embedding service (synchronous).
    
    Returns:
        EmbeddingService: Embedding service instance
        
    Note:
        This is for synchronous contexts. The model must already be initialized.
    """
    global _embedding_service
    if _embedding_service is None:
        raise ValueError("Embedding service not initialized")
    return _embedding_service
