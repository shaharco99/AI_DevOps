"""RAG document ingestion and processing."""

import logging
import uuid
from typing import Optional

from ai_devops_copilot.config.settings import settings
from ai_devops_copilot.rag.vector_store import get_vector_store_service

logger = logging.getLogger(__name__)


class DocumentIngestionService:
    """Handle document ingestion for RAG."""

    def __init__(self, chunk_size: int = settings.RAG_CHUNK_SIZE, chunk_overlap: int = settings.RAG_CHUNK_OVERLAP):
        """Initialize ingestion service.
        
        Args:
            chunk_size: Size of text chunks
            chunk_overlap: Overlap between chunks
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_text(self, text: str) -> list[str]:
        """Split text into chunks.
        
        Args:
            text: Text to chunk
            
        Returns:
            list: List of text chunks
        """
        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start = end - self.chunk_overlap
        return chunks

    def ingest_document(
        self,
        title: str,
        content: str,
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
            with open(file_path, "r", encoding="utf-8") as f:
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
