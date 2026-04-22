"""Embeddings initialization and management."""

import logging
from typing import Optional

from sentence_transformers import SentenceTransformer

from ai_devops_copilot.config.settings import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Embedding model service."""

    def __init__(self, model_name: str = settings.EMBEDDING_MODEL):
        """Initialize embedding service.
        
        Args:
            model_name: HuggingFace model name
        """
        self.model_name = model_name
        self.model: Optional[SentenceTransformer] = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the embedding model."""
        if self._initialized:
            return

        try:
            logger.info(f"Loading embedding model: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)
            self._initialized = True
            logger.info("Embedding model loaded successfully")
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
            embedding = self.model.encode(text, convert_to_tensor=False)
            return embedding.tolist()
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
            embeddings = self.model.encode(texts, convert_to_tensor=False)
            return embeddings.tolist()
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

        return self.model.get_sentence_embedding_dimension()


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
