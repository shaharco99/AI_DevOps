"""Common database queries."""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_devops_assistant.database.models import (
    ApplicationLog,
    ChatMessage,
    ChatSession,
    MetricSnapshot,
    PipelineLog,
    RAGDocument,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Chat Session Queries
# ============================================================================


async def create_chat_session(
    session: AsyncSession,
    user_id: str,
) -> ChatSession:
    """Create a new chat session.

    Args:
        session: Database session
        user_id: User ID

    Returns:
        ChatSession: Created session
    """
    chat_session = ChatSession(
        id=str(uuid.uuid4()),
        user_id=user_id,
    )
    session.add(chat_session)
    await session.commit()
    await session.refresh(chat_session)
    return chat_session


async def get_chat_session(
    session: AsyncSession,
    session_id: str,
) -> Optional[ChatSession]:
    """Get chat session by ID.

    Args:
        session: Database session
        session_id: Session ID

    Returns:
        ChatSession or None
    """
    result = await session.execute(select(ChatSession).where(ChatSession.id == session_id))
    return result.scalars().first()


async def add_chat_message(
    session: AsyncSession,
    session_id: str,
    role: str,
    content: str,
    tools_used: Optional[list] = None,
) -> ChatMessage:
    """Add message to chat session.

    Args:
        session: Database session
        session_id: Session ID
        role: Message role (user/assistant)
        content: Message content
        tools_used: Optional list of tools used

    Returns:
        ChatMessage: Created message
    """
    message = ChatMessage(
        id=str(uuid.uuid4()),
        session_id=session_id,
        role=role,
        content=content,
        tools_used=tools_used,
    )
    session.add(message)

    # Update message count
    chat_session = await get_chat_session(session, session_id)
    if chat_session:
        chat_session.message_count += 1

    await session.commit()
    await session.refresh(message)
    return message


async def get_chat_messages(
    session: AsyncSession,
    session_id: str,
    limit: int = 100,
) -> list[ChatMessage]:
    """Get chat messages for a session.

    Args:
        session: Database session
        session_id: Session ID
        limit: Maximum messages to return

    Returns:
        List of chat messages
    """
    result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


# ============================================================================
# Pipeline Log Queries
# ============================================================================


async def store_pipeline_log(
    session: AsyncSession,
    pipeline_id: str,
    run_number: int,
    status: str,
    log_content: str,
    error_summary: Optional[str] = None,
) -> PipelineLog:
    """Store pipeline log.

    Args:
        session: Database session
        pipeline_id: Pipeline ID
        run_number: Run number
        status: Pipeline status
        log_content: Log content
        error_summary: Optional error summary

    Returns:
        PipelineLog: Created log entry
    """
    log = PipelineLog(
        id=str(uuid.uuid4()),
        pipeline_id=pipeline_id,
        run_number=run_number,
        status=status,
        log_content=log_content,
        error_summary=error_summary,
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return log


async def get_pipeline_logs(
    session: AsyncSession,
    pipeline_id: str,
    limit: int = 50,
) -> list[PipelineLog]:
    """Get pipeline logs.

    Args:
        session: Database session
        pipeline_id: Pipeline ID
        limit: Maximum logs to return

    Returns:
        List of pipeline logs
    """
    result = await session.execute(
        select(PipelineLog)
        .where(PipelineLog.pipeline_id == pipeline_id)
        .order_by(PipelineLog.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


# ============================================================================
# Metric Queries
# ============================================================================


async def store_metric_snapshot(
    session: AsyncSession,
    service_name: str,
    metric_name: str,
    value: float,
    labels: Optional[dict] = None,
) -> MetricSnapshot:
    """Store metric snapshot.

    Args:
        session: Database session
        service_name: Service name
        metric_name: Metric name
        value: Metric value
        labels: Optional metric labels

    Returns:
        MetricSnapshot: Created metric
    """
    metric = MetricSnapshot(
        id=str(uuid.uuid4()),
        service_name=service_name,
        metric_name=metric_name,
        value=value,
        timestamp=datetime.utcnow(),
        labels=labels,
    )
    session.add(metric)
    await session.commit()
    await session.refresh(metric)
    return metric


async def get_metrics_by_service(
    session: AsyncSession,
    service_name: str,
    metric_name: Optional[str] = None,
    time_range_hours: int = 1,
    limit: int = 1000,
) -> list[MetricSnapshot]:
    """Get metrics for a service.

    Args:
        session: Database session
        service_name: Service name
        metric_name: Optional metric name filter
        time_range_hours: Time range in hours
        limit: Maximum metrics to return

    Returns:
        List of metrics
    """
    query = select(MetricSnapshot).where(
        MetricSnapshot.service_name == service_name,
        MetricSnapshot.timestamp >= datetime.utcnow() - timedelta(hours=time_range_hours),
    )

    if metric_name:
        query = query.where(MetricSnapshot.metric_name == metric_name)

    result = await session.execute(query.order_by(MetricSnapshot.timestamp.desc()).limit(limit))
    return result.scalars().all()


# ============================================================================
# RAG Document Queries
# ============================================================================


async def store_rag_document(
    session: AsyncSession,
    title: str,
    content: str,
    source: str,
    category: str,
    embedding_id: Optional[str] = None,
) -> RAGDocument:
    """Store RAG document.

    Args:
        session: Database session
        title: Document title
        content: Document content
        source: Document source
        category: Document category
        embedding_id: Optional embedding ID

    Returns:
        RAGDocument: Created document
    """
    doc = RAGDocument(
        id=str(uuid.uuid4()),
        title=title,
        content=content,
        source=source,
        category=category,
        embedding_id=embedding_id,
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return doc


async def get_rag_documents_by_category(
    session: AsyncSession,
    category: str,
    limit: int = 100,
) -> list[RAGDocument]:
    """Get RAG documents by category.

    Args:
        session: Database session
        category: Category name
        limit: Maximum documents to return

    Returns:
        List of RAG documents
    """
    result = await session.execute(
        select(RAGDocument)
        .where(RAGDocument.category == category)
        .order_by(RAGDocument.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


# ============================================================================
# Application Log Queries
# ============================================================================


async def store_application_log(
    session: AsyncSession,
    level: str,
    message: str,
    source: str,
    metadata: Optional[dict] = None,
) -> ApplicationLog:
    """Store application log.

    Args:
        session: Database session
        level: Log level
        message: Log message
        source: Log source
        metadata: Optional metadata

    Returns:
        ApplicationLog: Created log
    """
    log = ApplicationLog(
        id=str(uuid.uuid4()),
        level=level,
        message=message,
        source=source,
        metadata=metadata,
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return log


async def get_application_logs(
    session: AsyncSession,
    level: Optional[str] = None,
    time_range_hours: int = 24,
    limit: int = 500,
) -> list[ApplicationLog]:
    """Get application logs.

    Args:
        session: Database session
        level: Optional log level filter
        time_range_hours: Time range in hours
        limit: Maximum logs to return

    Returns:
        List of application logs
    """
    query = select(ApplicationLog).where(
        ApplicationLog.created_at >= datetime.utcnow() - timedelta(hours=time_range_hours)
    )

    if level:
        query = query.where(ApplicationLog.level == level)

    result = await session.execute(query.order_by(ApplicationLog.created_at.desc()).limit(limit))
    return result.scalars().all()
