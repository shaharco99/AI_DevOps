"""RAG retriever for semantic search."""

import logging
from typing import Any, Dict, List, Optional

from ai_devops_assistant.config.constants import RAG_SCORE_THRESHOLD, RAG_TOP_K
from ai_devops_assistant.rag.vector_store import get_vector_store_service

logger = logging.getLogger(__name__)


class RAGRetriever:
    """RAG retriever for semantic search with advanced filtering."""

    def __init__(
        self,
        top_k: int = RAG_TOP_K,
        score_threshold: float = RAG_SCORE_THRESHOLD,
        rerank: bool = False,
        diversity_bias: float = 0.0,
    ):
        """Initialize retriever.

        Args:
            top_k: Number of documents to retrieve
            score_threshold: Minimum similarity score
            rerank: Whether to rerank results
            diversity_bias: Diversity bias for result selection
        """
        self.top_k = top_k
        self.score_threshold = score_threshold
        self.rerank = rerank
        self.diversity_bias = diversity_bias

    def retrieve(
        self,
        query: str,
        category: Optional[str] = None,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
        metadata_filters: Optional[Dict[str, Any]] = None,
        include_content: bool = True,
        include_metadata: bool = True,
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant documents with advanced filtering.

        Args:
            query: Search query
            category: Optional category filter
            top_k: Override default top_k
            score_threshold: Override default score threshold
            metadata_filters: Additional metadata filters
            include_content: Whether to include document content
            include_metadata: Whether to include document metadata

        Returns:
            List of retrieved documents with scores
        """
        try:
            vector_store = get_vector_store_service()
            k = top_k or self.top_k
            threshold = score_threshold if score_threshold is not None else self.score_threshold

            # Build metadata filter
            where_filter = {}
            if category:
                where_filter["category"] = category
            if metadata_filters:
                where_filter.update(metadata_filters)

            where_filter = where_filter or None

            # Perform search
            results = vector_store.search(
                query=query,
                k=k * 2 if self.rerank else k,  # Get more results for reranking
                where=where_filter,
            )

            # Filter by score threshold
            filtered_results = []
            for result in results:
                score = result.get("score", 0.0)
                if score >= threshold:
                    filtered_results.append(result)

            # Apply diversity if enabled
            if self.diversity_bias > 0:
                filtered_results = self._apply_diversity(filtered_results)

            # Rerank if enabled
            if self.rerank:
                filtered_results = self._rerank_results(query, filtered_results)

            # Limit to top_k
            final_results = filtered_results[:k]

            # Format results
            formatted_results = []
            for result in final_results:
                doc = {
                    "score": result.get("score", 0.0),
                }

                if include_content:
                    doc["content"] = result.get("content", "")

                if include_metadata:
                    doc["metadata"] = result.get("metadata", {})

                formatted_results.append(doc)

            logger.info(f"Retrieved {len(formatted_results)} documents for query: {query[:50]}...")
            return formatted_results

        except Exception as e:
            logger.error(f"Failed to retrieve documents: {e}")
            return []

    def retrieve_with_hybrid(
        self,
        query: str,
        keyword_weight: float = 0.3,
        semantic_weight: float = 0.7,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Retrieve using hybrid search (keyword + semantic).

        Args:
            query: Search query
            keyword_weight: Weight for keyword search
            semantic_weight: Weight for semantic search
            **kwargs: Additional arguments for retrieve()

        Returns:
            List of retrieved documents
        """
        try:
            # Get semantic results
            semantic_results = self.retrieve(query, **kwargs)

            # Get keyword results using simple text matching
            keyword_results = self._keyword_search(query, **kwargs)

            # Combine results
            combined = self._combine_hybrid_results(
                semantic_results, keyword_results, semantic_weight, keyword_weight
            )

            return combined

        except Exception as e:
            logger.error(f"Failed hybrid search: {e}")
            return self.retrieve(query, **kwargs)

    def _keyword_search(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """Simple keyword-based search fallback."""
        try:
            vector_store = get_vector_store_service()

            # Get all documents (limited for performance)
            all_docs = vector_store.get_all_documents(limit=1000)

            query_terms = set(query.lower().split())
            scored_docs = []

            for doc in all_docs:
                content = doc.get("content", "").lower()
                metadata = doc.get("metadata", {})

                # Calculate keyword score
                score = 0
                for term in query_terms:
                    score += content.count(term)

                if score > 0:
                    scored_docs.append({
                        "content": doc.get("content", ""),
                        "metadata": metadata,
                        "score": min(score / len(query_terms), 1.0),  # Normalize
                    })

            # Sort by score and limit
            scored_docs.sort(key=lambda x: x["score"], reverse=True)
            return scored_docs[:kwargs.get("top_k", self.top_k)]

        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
            return []

    def _combine_hybrid_results(
        self,
        semantic: List[Dict[str, Any]],
        keyword: List[Dict[str, Any]],
        semantic_weight: float,
        keyword_weight: float
    ) -> List[Dict[str, Any]]:
        """Combine semantic and keyword results."""
        # Create combined scores
        combined_scores = {}

        # Add semantic scores
        for doc in semantic:
            content = doc.get("content", "")
            metadata = doc.get("metadata", {})
            key = (content, str(metadata))
            combined_scores[key] = {
                "content": content,
                "metadata": metadata,
                "score": doc.get("score", 0.0) * semantic_weight,
                "semantic_score": doc.get("score", 0.0),
                "keyword_score": 0.0,
            }

        # Add keyword scores
        for doc in keyword:
            content = doc.get("content", "")
            metadata = doc.get("metadata", {})
            key = (content, str(metadata))

            if key in combined_scores:
                combined_scores[key]["score"] += doc.get("score", 0.0) * keyword_weight
                combined_scores[key]["keyword_score"] = doc.get("score", 0.0)
            else:
                combined_scores[key] = {
                    "content": content,
                    "metadata": metadata,
                    "score": doc.get("score", 0.0) * keyword_weight,
                    "semantic_score": 0.0,
                    "keyword_score": doc.get("score", 0.0),
                }

        # Sort and return
        results = list(combined_scores.values())
        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    def _apply_diversity(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply diversity bias to results."""
        if not results or self.diversity_bias <= 0:
            return results

        # Simple diversity based on source
        seen_sources = set()
        diverse_results = []

        for result in results:
            source = result.get("metadata", {}).get("source", "")
            if source not in seen_sources or len(seen_sources) >= 3:
                diverse_results.append(result)
                seen_sources.add(source)

            if len(diverse_results) >= self.top_k:
                break

        return diverse_results

    def _rerank_results(self, query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Rerank results based on query relevance."""
        # Simple reranking based on exact term matches and position
        for result in results:
            content = result.get("content", "").lower()
            score_boost = 0

            # Boost for exact phrase matches
            if query.lower() in content:
                score_boost += 0.2

            # Boost for term frequency
            query_terms = query.lower().split()
            term_count = sum(content.count(term) for term in query_terms)
            score_boost += min(term_count * 0.1, 0.3)

            result["score"] = result.get("score", 0) + score_boost

        # Re-sort after reranking
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return results
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
