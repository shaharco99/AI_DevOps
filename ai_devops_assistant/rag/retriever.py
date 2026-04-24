"""RAG retriever for semantic search."""

import logging
from typing import Optional

from ai_devops_assistant.config.constants import RAG_SCORE_THRESHOLD, RAG_TOP_K
from ai_devops_assistant.rag.vector_store import get_vector_store_service

logger = logging.getLogger(__name__)


class RAGRetriever:
    """RAG retriever for semantic search."""

    def __init__(self, top_k: int = RAG_TOP_K, score_threshold: float = RAG_SCORE_THRESHOLD):
        """Initialize retriever.

        Args:
            top_k: Number of documents to retrieve
            score_threshold: Minimum similarity score
        """
        self.top_k = top_k
        self.score_threshold = score_threshold

    def retrieve(
        self,
        query: str,
        category: Optional[str] = None,
    ) -> list[dict]:
        """Retrieve relevant documents.

        Args:
            query: Search query
            category: Optional category filter

        Returns:
            list: List of retrieved documents
        """
        try:
            vector_store = get_vector_store_service()

            # Build metadata filter if category specified
            where_filter = None
            if category:
                where_filter = {"category": category}

            # Search
            results = vector_store.search(
                query=query,
                k=self.top_k,
                where=where_filter,
            )

            # Format results
            documents = []
            if results and results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    if results["distances"] and i < len(results["distances"][0]):
                        # Chroma returns distances, convert to similarity score
                        distance = results["distances"][0][i]
                        similarity = 1 / (1 + distance)  # Convert distance to similarity

                        if similarity >= self.score_threshold:
                            documents.append(
                                {
                                    "id": doc_id,
                                    "content": results["documents"][0][i],
                                    "metadata": results["metadatas"][0][i],
                                    "similarity": similarity,
                                }
                            )

            logger.info(f"Retrieved {len(documents)} documents for query: {query}")
            return documents

        except Exception as e:
            logger.error(f"Retrieval failed: {e}")
            return []

    def retrieve_by_category(
        self,
        category: str,
        limit: int = 10,
    ) -> list[dict]:
        """Retrieve documents by category.

        Args:
            category: Category name
            limit: Maximum documents to return

        Returns:
            list: List of documents
        """
        try:
            vector_store = get_vector_store_service()

            # Get all documents with category filter
            all_docs = vector_store.collection.get(
                where={"category": category},
                limit=limit,
            )

            documents = []
            if all_docs and all_docs["ids"]:
                for i, doc_id in enumerate(all_docs["ids"]):
                    documents.append(
                        {
                            "id": doc_id,
                            "content": all_docs["documents"][i],
                            "metadata": all_docs["metadatas"][i],
                        }
                    )

            logger.info(f"Retrieved {len(documents)} documents from category: {category}")
            return documents

        except Exception as e:
            logger.error(f"Category retrieval failed: {e}")
            return []

    def format_context(self, documents: list[dict]) -> str:
        """Format retrieved documents as context string.

        Args:
            documents: List of retrieved documents

        Returns:
            str: Formatted context
        """
        if not documents:
            return "No relevant documentation found."

        context_parts = []
        for i, doc in enumerate(documents, 1):
            metadata = doc.get("metadata", {})
            title = metadata.get("title", "Document")
            similarity = doc.get("similarity", 0)

            context_parts.append(
                f"[{i}] {title} (relevance: {similarity:.2%})\n{doc.get('content', '')}"
            )

        return "\n\n---\n\n".join(context_parts)


def get_rag_retriever(top_k: int = RAG_TOP_K) -> RAGRetriever:
    """Get RAG retriever instance.

    Returns:
        RAGRetriever: Retriever instance
    """
    return RAGRetriever(top_k=top_k)
