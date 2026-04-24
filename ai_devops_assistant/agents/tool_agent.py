"""Tool-capable AI agent orchestration."""

from __future__ import annotations

from ai_devops_assistant.agents.agent import DevOpsAgent
from ai_devops_assistant.rag.pipeline import SimpleRAGPipeline


class ToolAgent(DevOpsAgent):
    """Extends core agent with explicit RAG ingestion tool entrypoint."""

    def __init__(self):
        super().__init__()
        self.rag_pipeline = SimpleRAGPipeline()

    async def ingest_knowledge_url(self, url: str) -> int:
        """Scrape + ingest a URL for future retrieval."""
        return await self.rag_pipeline.ingest_website(url)
