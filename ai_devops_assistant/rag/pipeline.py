"""RAG ingestion and retrieval pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ai_devops_assistant.rag.scraper import ScrapedContent, WebScraper

logger = logging.getLogger(__name__)


@dataclass
class RAGDocument:
    """Internal RAG document representation."""

    content: str
    metadata: dict[str, Any]


class SimpleRAGPipeline:
    """Minimal RAG pipeline with chunking and in-memory retrieval."""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 100):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._documents: list[RAGDocument] = []

    def ingest_text(self, content: str, metadata: dict[str, Any]) -> int:
        """Chunk and ingest text content."""
        if not content.strip():
            return 0
        chunks = self._chunk_text(content)
        for idx, chunk in enumerate(chunks):
            chunk_meta = dict(metadata)
            chunk_meta["chunk_index"] = idx
            self._documents.append(RAGDocument(content=chunk, metadata=chunk_meta))
        logger.info("rag_ingested", extra={"chunks": len(chunks), "source": metadata.get("source")})
        return len(chunks)

    async def ingest_website(self, url: str) -> int:
        """Scrape website and ingest text."""
        scraper = WebScraper()
        try:
            scraped = await scraper.scrape_url(url)
            if scraped is None:
                return 0
            return self.ingest_scraped(scraped)
        finally:
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
