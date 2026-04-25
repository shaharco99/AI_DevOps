"""Chroma vector store management."""

import logging
import os
from typing import Optional

import chromadb
from chromadb.config import Settings

from ai_devops_assistant.config.settings import settings
from ai_devops_assistant.rag.embeddings import get_embedding_service_sync

logger = logging.getLogger(__name__)


class VectorStoreService:
    """Chroma vector store service."""

    def __init__(self, persist_dir: str = settings.CHROMA_PERSIST_DIR):
        """Initialize vector store.

        Args:
            persist_dir: Directory to persist vector database
        """
        self.persist_dir = persist_dir
        self.client: Optional[chromadb.Client] = None
        self.collection: Optional[chromadb.Collection] = None
        self._initialized = False

    def initialize(self) -> None:
        """Initialize the vector store."""
        if self._initialized:
            return

        try:
            # Create persist directory if it doesn't exist
            os.makedirs(self.persist_dir, exist_ok=True)

            logger.info(f"Initializing Chroma with persist dir: {self.persist_dir}")

            # Create Chroma client with persistence
            chroma_settings = Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=self.persist_dir,
                anonymized_telemetry=settings.CHROMA_ANONYMIZED_TELEMETRY,
            )

            self.client = chromadb.Client(chroma_settings)

            # Get or create collection
            self.collection = self.client.get_or_create_collection(
                name="devops_knowledge",
                metadata={"hnsw:space": "cosine"},
            )

            self._initialized = True
            logger.info("Vector store initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}")
            raise

    def add_documents(
        self,
        documents: list[str],
        ids: list[str],
        metadatas: Optional[list[dict]] = None,
    ) -> None:
        """Add documents to vector store.

        Args:
            documents: List of document texts
            ids: List of document IDs
            metadatas: Optional list of metadata dicts

        Raises:
            ValueError: If not initialized
        """
        if not self._initialized or self.collection is None:
            raise ValueError("Vector store not initialized")

        try:
            # Get embeddings
            embedding_service = get_embedding_service_sync()
            embeddings = embedding_service.embed_batch(documents)

            # Add to collection
            self.collection.add(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas or [{} for _ in documents],
            )

            logger.info(f"Added {len(documents)} documents to vector store")

        except Exception as e:
            logger.error(f"Failed to add documents: {e}")
            raise

    def search(
        self,
        query: str,
        k: int = 5,
        where: Optional[dict] = None,
    ) -> List[Dict[str, Any]]:
        """Search vector store.

        Args:
            query: Search query
            k: Number of results to return
            where: Optional metadata filter

        Returns:
            List of search results with content, metadata, and scores

        Raises:
            ValueError: If not initialized
        """
        if not self._initialized or self.collection is None:
            raise ValueError("Vector store not initialized")

        try:
            # Get query embedding
            embedding_service = get_embedding_service_sync()
            query_embedding = embedding_service.embed(query)

            # Search
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=k,
                where=where,
            )

            # Format results
            formatted_results = []
            if results and results["documents"]:
                for i, doc in enumerate(results["documents"][0]):
                    result = {
                        "content": doc,
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "score": 1.0 - results["distances"][0][i] if results["distances"] else 0.0,
                    }
                    formatted_results.append(result)

            return formatted_results

        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise

    def get_all_documents(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get all documents (limited for performance).

        Args:
            limit: Maximum number of documents to return

        Returns:
            List of all documents
        """
        if not self._initialized or self.collection is None:
            raise ValueError("Vector store not initialized")

        try:
            results = self.collection.get(limit=limit)
            documents = []

            if results and results["documents"]:
                for i, doc in enumerate(results["documents"]):
                    documents.append({
                        "content": doc,
                        "metadata": results["metadatas"][i] if results["metadatas"] else {},
                        "id": results["ids"][i] if results["ids"] else f"doc_{i}",
                    })

            return documents

        except Exception as e:
            logger.error(f"Failed to get all documents: {e}")
            return []

    def get_collection_count(self) -> int:
        """Get total number of documents in collection.

        Returns:
            Number of documents
        """
        return self.count()

    def clear_collection(self) -> None:
        """Clear all documents from collection."""
        self.delete_all()

    def get_document(self, doc_id: str) -> Optional[dict]:
        """Get document by ID.

        Args:
            doc_id: Document ID

        Returns:
            dict: Document data or None

        Raises:
            ValueError: If not initialized
        """
        if not self._initialized or self.collection is None:
            raise ValueError("Vector store not initialized")

        try:
            result = self.collection.get(ids=[doc_id])
            if result and result["ids"]:
                return {
                    "id": result["ids"][0],
                    "document": result["documents"][0],
                    "metadata": result["metadatas"][0],
                }
            return None

        except Exception as e:
            logger.error(f"Failed to get document: {e}")
            raise

    def delete_document(self, doc_id: str) -> None:
        """Delete document from vector store.

        Args:
            doc_id: Document ID

        Raises:
            ValueError: If not initialized
        """
        if not self._initialized or self.collection is None:
            raise ValueError("Vector store not initialized")

        try:
            self.collection.delete(ids=[doc_id])
            logger.info(f"Deleted document: {doc_id}")

        except Exception as e:
            logger.error(f"Failed to delete document: {e}")
            raise

    def delete_all(self) -> None:
        """Delete all documents from collection.

        Raises:
            ValueError: If not initialized
        """
        if not self._initialized or self.collection is None:
            raise ValueError("Vector store not initialized")

        try:
            # Get all documents and delete them
            all_docs = self.collection.get()
            if all_docs["ids"]:
                self.collection.delete(ids=all_docs["ids"])
                logger.info(f"Deleted {len(all_docs['ids'])} documents")

        except Exception as e:
            logger.error(f"Failed to delete all documents: {e}")
            raise

    def count(self) -> int:
        """Get document count.

        Returns:
            int: Number of documents

        Raises:
            ValueError: If not initialized
        """
        if not self._initialized or self.collection is None:
            raise ValueError("Vector store not initialized")

        try:
            return self.collection.count()
        except Exception as e:
            logger.error(f"Failed to get count: {e}")
            raise


# Global instance
_vector_store_service: Optional[VectorStoreService] = None


def get_vector_store_service() -> VectorStoreService:
    """Get or create vector store service.

    Returns:
        VectorStoreService: Vector store service instance
    """
    global _vector_store_service
    if _vector_store_service is None:
        _vector_store_service = VectorStoreService()
        _vector_store_service.initialize()
    return _vector_store_service
