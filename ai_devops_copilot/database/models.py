"""SQLAlchemy ORM models."""

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, mapped_column

Base = declarative_base()


class PipelineLog(Base):
    """Pipeline execution logs."""

    __tablename__ = "pipeline_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    pipeline_id: Mapped[str] = mapped_column(String(256))
    run_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(50))  # success, failed, running
    log_content: Mapped[str] = mapped_column(Text)
    error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<PipelineLog(id={self.id}, status={self.status})>"


class MetricSnapshot(Base):
    """Prometheus metric snapshots."""

    __tablename__ = "metric_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    service_name: Mapped[str] = mapped_column(String(256))
    metric_name: Mapped[str] = mapped_column(String(256))
    value: Mapped[float] = mapped_column()
    timestamp: Mapped[datetime] = mapped_column(DateTime)
    labels: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    def __repr__(self) -> str:
        return f"<MetricSnapshot(metric={self.metric_name}, value={self.value})>"


class RAGDocument(Base):
    """RAG knowledge base documents."""

    __tablename__ = "rag_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(512))
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(512))  # URL or file path
    category: Mapped[str] = mapped_column(String(256))
    embedding_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<RAGDocument(id={self.id}, title={self.title})>"


class ChatSession(Base):
    """Chat session management."""

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(256))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<ChatSession(id={self.id}, user_id={self.user_id})>"


class ChatMessage(Base):
    """Chat messages."""

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36))
    role: Mapped[str] = mapped_column(String(50))  # user, assistant
    content: Mapped[str] = mapped_column(Text)
    tools_used: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    def __repr__(self) -> str:
        return f"<ChatMessage(id={self.id}, role={self.role})>"


class ApplicationLog(Base):
    """Application logs."""

    __tablename__ = "application_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    level: Mapped[str] = mapped_column(String(50))  # INFO, ERROR, WARNING, etc.
    message: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(256))
    metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    def __repr__(self) -> str:
        return f"<ApplicationLog(id={self.id}, level={self.level})>"
