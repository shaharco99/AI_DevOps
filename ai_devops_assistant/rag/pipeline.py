"""RAG ingestion and retrieval pipeline."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from ai_devops_assistant.config.settings import settings
from ai_devops_assistant.rag.document_ingestion import DocumentIngestionService, DocumentLoader
from ai_devops_assistant.rag.embeddings import get_embedding_service
from ai_devops_assistant.rag.retriever import RAGRetriever
from ai_devops_assistant.rag.scraper import WebScraper
from ai_devops_assistant.rag.vector_store import get_vector_store_service

logger = logging.getLogger(__name__)


@dataclass
class RAGDocument:
    """Internal RAG document representation."""

    content: str
    metadata: Dict[str, Any]
    score: Optional[float] = None


@dataclass
class RAGQuery:
    """RAG query with parameters."""

    query: str
    top_k: int = 5
    score_threshold: Optional[float] = None
    category_filter: Optional[str] = None
    metadata_filters: Optional[Dict[str, Any]] = None


@dataclass
class RAGResult:
    """RAG retrieval result."""

    query: str
    documents: List[RAGDocument]
    total_found: int
    execution_time: float


class RAGPipeline:
    """Complete RAG pipeline with ingestion and retrieval."""

    def __init__(
        self,
        chunk_size: int = settings.RAG_CHUNK_SIZE,
        chunk_overlap: int = settings.RAG_CHUNK_OVERLAP,
        chunk_strategy: str = "fixed",
        embedding_model: str = settings.EMBEDDING_MODEL,
    ):
        """Initialize RAG pipeline.

        Args:
            chunk_size: Size of text chunks
            chunk_overlap: Overlap between chunks
            chunk_strategy: Text chunking strategy
            embedding_model: Embedding model to use
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.chunk_strategy = chunk_strategy
        self.embedding_model = embedding_model

        # Initialize components
        self.ingestion_service = DocumentIngestionService(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            chunk_strategy=chunk_strategy
        )
        self.retriever = RAGRetriever()
        self.scraper = WebScraper()
        self.loader = DocumentLoader()

        self._initialized = False

    async def initialize(self) -> None:
        """Initialize all RAG components."""
        if self._initialized:
            return

        try:
            logger.info("Initializing RAG pipeline...")

            # Initialize embedding service
            embedding_service = await get_embedding_service()
            await embedding_service.initialize()

            # Initialize vector store
            vector_store = get_vector_store_service()
            vector_store.initialize()

            self._initialized = True
            logger.info("RAG pipeline initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize RAG pipeline: {e}")
            raise

    async def ingest_text(
        self,
        content: str,
        metadata: Dict[str, Any],
        chunk_strategy: Optional[str] = None
    ) -> int:
        """Ingest text content into RAG system.

        Args:
            content: Text content to ingest
            metadata: Document metadata
            chunk_strategy: Optional chunking strategy override

        Returns:
            Number of chunks ingested
        """
        await self.initialize()
        return self.ingestion_service.ingest_text(content, metadata, chunk_strategy)

    async def ingest_file(
        self,
        file_path: Union[str, "Path"],
        metadata: Optional[Dict[str, Any]] = None,
        chunk_strategy: Optional[str] = None
    ) -> int:
        """Ingest document from file.

        Args:
            file_path: Path to file
            metadata: Additional metadata
            chunk_strategy: Optional chunking strategy override

        Returns:
            Number of chunks ingested
        """
        await self.initialize()
        return self.ingestion_service.ingest_file(file_path, metadata, chunk_strategy)

    async def ingest_url(
        self,
        url: str,
        metadata: Optional[Dict[str, Any]] = None,
        chunk_strategy: Optional[str] = "paragraph"
    ) -> int:
        """Ingest content from URL.

        Args:
            url: URL to scrape and ingest
            metadata: Additional metadata
            chunk_strategy: Optional chunking strategy override

        Returns:
            Number of chunks ingested
        """
        await self.initialize()

        try:
            # Scrape content
            scraped = await self.scraper.scrape_url(url)
            if scraped is None:
                logger.warning(f"Failed to scrape content from {url}")
                return 0

            # Prepare metadata
            url_metadata = {
                "source": url,
                "title": scraped.title,
                "source_type": "web",
                **scraped.metadata
            }
            if metadata:
                url_metadata.update(metadata)

            # Ingest content
            return self.ingestion_service.ingest_text(
                scraped.content,
                url_metadata,
                chunk_strategy
            )

        except Exception as e:
            logger.error(f"Failed to ingest URL {url}: {e}")
            return 0

    async def ingest_sitemap(
        self,
        sitemap_url: str,
        metadata: Optional[Dict[str, Any]] = None,
        max_pages: int = 10,
        chunk_strategy: Optional[str] = "paragraph"
    ) -> int:
        """Ingest all pages from a sitemap.

        Args:
            sitemap_url: URL of sitemap
            metadata: Additional metadata for all pages
            max_pages: Maximum number of pages to ingest
            chunk_strategy: Optional chunking strategy override

        Returns:
            Total number of chunks ingested
        """
        await self.initialize()

        try:
            from ai_devops_assistant.rag.scraper import SitemapScraper
            sitemap_scraper = SitemapScraper()

            urls = await sitemap_scraper.discover_urls(sitemap_url, max_pages)
            logger.info(f"Found {len(urls)} URLs in sitemap")

            total_chunks = 0
            for url in urls:
                chunks = await self.ingest_url(url, metadata, chunk_strategy)
                total_chunks += chunks
                await asyncio.sleep(1)  # Rate limiting

            logger.info(f"Ingested {total_chunks} chunks from {len(urls)} sitemap URLs")
            return total_chunks

        except Exception as e:
            logger.error(f"Failed to ingest sitemap {sitemap_url}: {e}")
            return 0

    async def query(
        self,
        query: Union[str, RAGQuery],
        include_metadata: bool = True
    ) -> RAGResult:
        """Query the RAG system.

        Args:
            query: Query string or RAGQuery object
            include_metadata: Whether to include document metadata

        Returns:
            RAGResult with retrieved documents
        """
        await self.initialize()

        import time
        start_time = time.time()

        # Parse query
        if isinstance(query, str):
            rag_query = RAGQuery(query=query)
        else:
            rag_query = query

        try:
            # Perform retrieval
            results = self.retriever.retrieve(
                query=rag_query.query,
                category=rag_query.category_filter,
                top_k=rag_query.top_k,
            )

            # Convert to RAGDocument objects
            documents = []
            for result in results:
                doc = RAGDocument(
                    content=result.get("content", ""),
                    metadata=result.get("metadata", {}) if include_metadata else {},
                    score=result.get("score")
                )
                documents.append(doc)

            execution_time = time.time() - start_time

            return RAGResult(
                query=rag_query.query,
                documents=documents,
                total_found=len(documents),
                execution_time=execution_time
            )

        except Exception as e:
            logger.error(f"Failed to query RAG system: {e}")
            execution_time = time.time() - start_time
            return RAGResult(
                query=rag_query.query,
                documents=[],
                total_found=0,
                execution_time=execution_time
            )

    async def get_stats(self) -> Dict[str, Any]:
        """Get RAG system statistics.

        Returns:
            Dictionary with system statistics
        """
        await self.initialize()

        try:
            vector_store = get_vector_store_service()
            collection_count = vector_store.get_collection_count()
            return {
                "total_documents": collection_count,
                "chunk_size": self.chunk_size,
                "chunk_overlap": self.chunk_overlap,
                "chunk_strategy": self.chunk_strategy,
                "embedding_model": self.embedding_model,
            }
        except Exception as e:
            logger.error(f"Failed to get RAG stats: {e}")
            return {"error": str(e)}

    async def clear_index(self) -> bool:
        """Clear all documents from the index.

        Returns:
            True if successful
        """
        try:
            vector_store = get_vector_store_service()
            vector_store.clear_collection()
            logger.info("RAG index cleared")
            return True
        except Exception as e:
            logger.error(f"Failed to clear RAG index: {e}")
            return False


# Backward compatibility
class SimpleRAGPipeline(RAGPipeline):
    """Backward compatibility wrapper."""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 100):
        super().__init__(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    def ingest_text(self, content: str, metadata: Dict[str, Any]) -> int:
        """Synchronous ingestion for backward compatibility."""
        # Run async method in event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is already running, we need to handle differently
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.ingest_text_async(content, metadata))
                    return future.result()
            else:
                return loop.run_until_complete(self.ingest_text_async(content, metadata))
        except Exception:
            # Fallback to async run
            return asyncio.run(self.ingest_text_async(content, metadata))

    async def ingest_text_async(self, content: str, metadata: Dict[str, Any]) -> int:
        """Async ingestion method."""
        return await super().ingest_text(content, metadata)

    def retrieve(self, query: str, k: int = 5) -> List[RAGDocument]:
        """Synchronous retrieval for backward compatibility."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.query_async(query, k))
                    result = future.result()
                    return result.documents
            else:
                result = loop.run_until_complete(self.query_async(query, k))
                return result.documents
        except Exception:
            result = asyncio.run(self.query_async(query, k))
            return result.documents

    async def query_async(self, query: str, k: int = 5) -> RAGResult:
        """Async query method."""
        rag_query = RAGQuery(query=query, top_k=k)
        return await super().query(rag_query)
            await scraper.close()

    def ingest_scraped(self, scraped: ScrapedContent) -> int:
        """Ingest a `ScrapedContent` object."""
        metadata = {"source": "web", "url": scraped.url, "title": scraped.title, **scraped.metadata}
        return self.ingest_text(scraped.content, metadata)

    def retrieve(self, query: str, k: int = 5) -> list[RAGDocument]:
        """Simple lexical retrieval for local usage and tests."""
        query_terms = {t for t in query.lower().split() if t}
        scored: list[tuple[int, RAGDocument]] = []
        for doc in self._documents:
            text = doc.content.lower()
            score = sum(1 for term in query_terms if term in text)
            if score > 0:
                scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored[:k]]

    def _chunk_text(self, text: str) -> list[str]:
        if len(text) <= self.chunk_size:
            return [text]
        chunks: list[str] = []
        start = 0
        step = max(1, self.chunk_size - self.chunk_overlap)
        while start < len(text):
            chunks.append(text[start : start + self.chunk_size])
            start += step
        return chunks
