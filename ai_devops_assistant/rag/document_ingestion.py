"""RAG document ingestion and processing."""

import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ai_devops_assistant.config.settings import settings
from ai_devops_assistant.rag.vector_store import get_vector_store_service

logger = logging.getLogger(__name__)


class TextChunker:
    """Advanced text chunking strategies."""

    def __init__(
        self,
        chunk_size: int = settings.RAG_CHUNK_SIZE,
        chunk_overlap: int = settings.RAG_CHUNK_OVERLAP,
        strategy: str = "fixed",  # fixed, sentence, paragraph
    ):
        """Initialize chunker.

        Args:
            chunk_size: Size of text chunks
            chunk_overlap: Overlap between chunks
            strategy: Chunking strategy
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.strategy = strategy

    def chunk_text(self, text: str) -> List[str]:
        """Split text into chunks using specified strategy.

        Args:
            text: Text to chunk

        Returns:
            List of text chunks
        """
        if self.strategy == "sentence":
            return self._chunk_by_sentence(text)
        elif self.strategy == "paragraph":
            return self._chunk_by_paragraph(text)
        else:
            return self._chunk_fixed(text)

    def _chunk_fixed(self, text: str) -> List[str]:
        """Fixed-size chunking."""
        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]
            if chunk.strip():  # Only add non-empty chunks
                chunks.append(chunk)
            start = end - self.chunk_overlap
        return chunks

    def _chunk_by_sentence(self, text: str) -> List[str]:
        """Chunk by sentences."""
        import re
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks = []
        current_chunk = ""

        for sentence in sentences:
            if len(current_chunk) + len(sentence) <= self.chunk_size:
                current_chunk += sentence + " "
            else:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + " "

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks

    def _chunk_by_paragraph(self, text: str) -> List[str]:
        """Chunk by paragraphs."""
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) <= self.chunk_size:
                current_chunk += para + "\n\n"
            else:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = para + "\n\n"

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks


class DocumentLoader:
    """Load documents from various sources."""

    def __init__(self):
        self.chunkers = {
            "fixed": TextChunker(strategy="fixed"),
            "sentence": TextChunker(strategy="sentence"),
            "paragraph": TextChunker(strategy="paragraph"),
        }

    def load_text(
        self,
        content: str,
        metadata: Dict[str, Any],
        chunk_strategy: str = "fixed"
    ) -> List[Dict[str, Any]]:
        """Load text content.

        Args:
            content: Text content
            metadata: Document metadata
            chunk_strategy: Chunking strategy

        Returns:
            List of document chunks with metadata
        """
        chunker = self.chunkers.get(chunk_strategy, self.chunkers["fixed"])
        chunks = chunker.chunk_text(content)

        documents = []
        for i, chunk in enumerate(chunks):
            doc_metadata = dict(metadata)
            doc_metadata.update({
                "chunk_index": i,
                "total_chunks": len(chunks),
                "chunk_strategy": chunk_strategy,
            })
            documents.append({
                "content": chunk,
                "metadata": doc_metadata,
                "id": str(uuid.uuid4()),
            })

        return documents

    def load_file(
        self,
        file_path: Union[str, Path],
        metadata: Optional[Dict[str, Any]] = None,
        chunk_strategy: str = "fixed"
    ) -> List[Dict[str, Any]]:
        """Load document from file.

        Args:
            file_path: Path to file
            metadata: Additional metadata
            chunk_strategy: Chunking strategy

        Returns:
            List of document chunks
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Read file content
        if path.suffix.lower() in ['.md', '.txt', '.py', '.yaml', '.yml', '.json']:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        else:
            raise ValueError(f"Unsupported file type: {path.suffix}")

        # Prepare metadata
        file_metadata = {
            "source": str(path),
            "filename": path.name,
            "file_type": path.suffix,
            "file_size": path.stat().st_size,
        }
        if metadata:
            file_metadata.update(metadata)

        return self.load_text(content, file_metadata, chunk_strategy)

    def load_url(
        self,
        url: str,
        metadata: Optional[Dict[str, Any]] = None,
        chunk_strategy: str = "fixed"
    ) -> List[Dict[str, Any]]:
        """Load document from URL (requires content to be provided).

        Args:
            url: URL source
            metadata: Additional metadata
            chunk_strategy: Chunking strategy

        Returns:
            List of document chunks (content must be provided separately)
        """
        url_metadata = {
            "source": url,
            "source_type": "url",
        }
        if metadata:
            url_metadata.update(metadata)

        # Note: Actual content loading should be done by scraper
        return []


class DocumentIngestionService:
    """Handle document ingestion for RAG."""

    def __init__(
        self,
        chunk_size: int = settings.RAG_CHUNK_SIZE,
        chunk_overlap: int = settings.RAG_CHUNK_OVERLAP,
        chunk_strategy: str = "fixed",
    ):
        """Initialize ingestion service.

        Args:
            chunk_size: Size of text chunks
            chunk_overlap: Overlap between chunks
            chunk_strategy: Default chunking strategy
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.chunk_strategy = chunk_strategy
        self.loader = DocumentLoader()
        self.vector_store = get_vector_store_service()

    def ingest_text(
        self,
        content: str,
        metadata: Dict[str, Any],
        chunk_strategy: Optional[str] = None
    ) -> int:
        """Ingest text content.

        Args:
            content: Text content
            metadata: Document metadata
            chunk_strategy: Optional chunking strategy override

        Returns:
            Number of chunks ingested
        """
        strategy = chunk_strategy or self.chunk_strategy
        documents = self.loader.load_text(content, metadata, strategy)

        if not documents:
            return 0

        # Add to vector store
        self.vector_store.add_documents(
            documents=[doc["content"] for doc in documents],
            ids=[doc["id"] for doc in documents],
            metadatas=[doc["metadata"] for doc in documents],
        )

        logger.info(f"Ingested {len(documents)} chunks from text")
        return len(documents)

    def ingest_file(
        self,
        file_path: Union[str, Path],
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
        strategy = chunk_strategy or self.chunk_strategy
        documents = self.loader.load_file(file_path, metadata, strategy)

        if not documents:
            return 0

        # Add to vector store
        self.vector_store.add_documents(
            documents=[doc["content"] for doc in documents],
            ids=[doc["id"] for doc in documents],
            metadatas=[doc["metadata"] for doc in documents],
        )

        logger.info(f"Ingested {len(documents)} chunks from file: {file_path}")
        return len(documents)

    def ingest_documents(
        self,
        documents: List[Dict[str, Any]],
    ) -> int:
        """Ingest multiple documents.

        Args:
            documents: List of document dicts with 'content', 'metadata', 'id' keys

        Returns:
            Total number of chunks ingested
        """
        if not documents:
            return 0

        # Add to vector store
        self.vector_store.add_documents(
            documents=[doc["content"] for doc in documents],
            ids=[doc.get("id", str(uuid.uuid4())) for doc in documents],
            metadatas=[doc.get("metadata", {}) for doc in documents],
        )

        logger.info(f"Ingested {len(documents)} documents")
        return len(documents)
        source: str,
        category: str = "general",
    ) -> None:
        """Ingest a document into RAG system.

        Args:
            title: Document title
            content: Document content
            source: Document source (URL, file path, etc.)
            category: Document category

        Raises:
            ValueError: If ingestion fails
        """
        try:
            # Chunk document
            chunks = self.chunk_text(content)
            logger.info(f"Ingesting '{title}' with {len(chunks)} chunks")

            # Generate IDs and metadatas
            doc_ids = [str(uuid.uuid4()) for _ in chunks]
            metadatas = [
                {
                    "title": title,
                    "source": source,
                    "category": category,
                    "chunk_index": i,
                }
                for i in range(len(chunks))
            ]

            # Add to vector store
            vector_store = get_vector_store_service()
            vector_store.add_documents(
                documents=chunks,
                ids=doc_ids,
                metadatas=metadatas,
            )

            logger.info(f"Successfully ingested '{title}'")

        except Exception as e:
            logger.error(f"Failed to ingest document '{title}': {e}")
            raise

    def ingest_documents(
        self,
        documents: list[dict],
    ) -> None:
        """Ingest multiple documents.

        Args:
            documents: List of dicts with 'title', 'content', 'source', 'category'

        Raises:
            ValueError: If ingestion fails
        """
        for doc in documents:
            self.ingest_document(
                title=doc.get("title"),
                content=doc.get("content"),
                source=doc.get("source"),
                category=doc.get("category", "general"),
            )

    def ingest_from_file(
        self,
        file_path: str,
        category: str = "general",
    ) -> None:
        """Ingest document from file.

        Args:
            file_path: Path to file
            category: Document category

        Raises:
            ValueError: If file not found or reading fails
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            title = file_path.split("/")[-1]
            self.ingest_document(
                title=title,
                content=content,
                source=file_path,
                category=category,
            )

        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
            raise
        except Exception as e:
            logger.error(f"Failed to ingest from file '{file_path}': {e}")
            raise


def load_devops_documentation() -> None:
    """Load default DevOps documentation into RAG system."""
    ingestion_service = DocumentIngestionService()

    # Kubernetes documentation snippets
    k8s_docs = [
        {
            "title": "Kubernetes Pods",
            "content": """
Pods are the smallest deployable units in Kubernetes.

Key concepts:
- Pods are ephemeral and can be created and destroyed
- Each pod gets a unique IP address
- Containers in a pod share network namespace
- Pods are typically managed by controllers like Deployments

Common pod issues:
- CrashLoopBackOff: Container keeps crashing
- ImagePullBackOff: Cannot pull container image
- Pending: Pod waiting for resources
- OOMKilled: Out of memory error

Debugging commands:
- kubectl get pods
- kubectl describe pod <pod-name>
- kubectl logs <pod-name>
- kubectl exec -it <pod-name> -- /bin/sh
""",
            "source": "kubernetes-docs",
            "category": "kubernetes",
        },
        {
            "title": "Kubernetes Deployments",
            "content": """
Deployments manage ReplicaSets and provide declarative updates for Pods.

Features:
- Declarative updates of pods and ReplicaSets
- Rollback to previous revision
- Scaling and rolling updates
- Pause and resume deployment

Deployment status:
- Available: Replicas are available
- Updated: Replicas have been updated
- Total: Total number of replicas

Common deployment issues:
- Replicas not scaling to desired count
- Failed rollout due to image error
- Resource quota exceeded

Best practices:
- Use readiness probes
- Set resource requests and limits
- Use rolling updates for zero downtime
""",
            "source": "kubernetes-docs",
            "category": "kubernetes",
        },
    ]

    # Docker documentation snippets
    docker_docs = [
        {
            "title": "Docker Best Practices",
            "content": """
Docker Best Practices for Production:

Image optimization:
- Use minimal base images (alpine)
- Multi-stage builds to reduce image size
- Layer caching for faster builds
- Use .dockerignore to exclude files

Container runtime:
- Run as non-root user
- Use read-only root filesystem when possible
- Set resource limits (memory, CPU)
- Use health checks

Security:
- Scan images for vulnerabilities
- Use private registries
- Sign images
- Minimize privileges

Performance:
- Cache dependencies
- Use layer caching
- Optimize build context
""",
            "source": "docker-docs",
            "category": "docker",
        },
    ]

    # CI/CD documentation snippets
    cicd_docs = [
        {
            "title": "CI/CD Pipeline Best Practices",
            "content": """
Continuous Integration and Deployment Principles:

Pipeline stages:
1. Build: Compile code and dependencies
2. Test: Run unit, integration, and E2E tests
3. Security: Scan for vulnerabilities
4. Deploy: Release to environment
5. Monitor: Track application health

Recommendations:
- Fast feedback (< 10 minutes for CI)
- Automated testing (unit, integration, E2E)
- Immutable artifacts
- Environment parity
- Blue-green or canary deployments

Common issues:
- Flaky tests causing false negatives
- Long build times slowing feedback
- Inconsistent environments
- Manual deployment steps

Metrics:
- Lead time for changes
- Deployment frequency
- Time to recover from failures
- Change failure rate
""",
            "source": "cicd-docs",
            "category": "cicd",
        },
    ]

    # Monitoring documentation snippets
    monitoring_docs = [
        {
            "title": "Observability and Monitoring",
            "content": """
Observability is about understanding system behavior through external outputs.

Three pillars:
1. Logs: Discrete events
2. Metrics: Time-series measurements
3. Traces: Request flows

Key metrics to monitor:
- Request latency (p50, p95, p99)
- Error rate
- Throughput (requests/sec)
- Resource usage (CPU, memory)
- Dependency health

Alert strategy:
- Alert on symptoms, not causes
- Avoid alert fatigue
- Set appropriate thresholds
- Use runbooks for common issues

Tools:
- Prometheus for metrics
- Grafana for visualization
- ELK stack for logs
- Jaeger for tracing
""",
            "source": "monitoring-docs",
            "category": "monitoring",
        },
    ]

    try:
        logger.info("Loading DevOps documentation into RAG system")
        ingestion_service.ingest_documents(k8s_docs)
        ingestion_service.ingest_documents(docker_docs)
        ingestion_service.ingest_documents(cicd_docs)
        ingestion_service.ingest_documents(monitoring_docs)
        logger.info("DevOps documentation loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load DevOps documentation: {e}")


# Initialize on import
try:
    if settings.ENABLE_RAG:
        logger.info("RAG system enabled, loading documentation")
        load_devops_documentation()
except Exception as e:
    logger.warning(f"Could not initialize RAG system: {e}")
