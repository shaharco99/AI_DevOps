"""Application settings and configuration management."""

import logging
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings from environment variables."""

    # ========================================================================
    # Application Settings
    # ========================================================================
    APP_NAME: str = "AI DevOps Copilot"
    APP_VERSION: str = "0.1.0"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_LOG_LEVEL: str = "INFO"
    API_ENVIRONMENT: str = "development"
    SECRET_KEY: str = "your-secret-key-change-this-in-production"
    ALLOWED_HOSTS: list[str] = ["localhost", "127.0.0.1"]

    # ========================================================================
    # Database Settings
    # ========================================================================
    DATABASE_URL: str = "postgresql+asyncpg://copilot_user:copilot_password@localhost:5432/copilot"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 40
    DATABASE_ECHO: bool = False
    DATABASE_SSL_MODE: str = "disable"

    # ========================================================================
    # LLM Settings
    # ========================================================================
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    LLM_MODEL: str = "llama3"
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 2048
    LLM_TIMEOUT: int = 60

    # ========================================================================
    # Vector Database Settings
    # ========================================================================
    CHROMA_PERSIST_DIR: str = "/data/chroma"
    CHROMA_ANONYMIZED_TELEMETRY: bool = False
    MAX_RAG_DOCUMENTS: int = 1000

    # ========================================================================
    # RAG Settings
    # ========================================================================
    RAG_CHUNK_SIZE: int = 1000
    RAG_CHUNK_OVERLAP: int = 100
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # ========================================================================
    # Kubernetes Settings
    # ========================================================================
    KUBECONFIG: Optional[str] = None
    K8S_NAMESPACE: str = "default"
    K8S_VERIFY_SSL: bool = True
    K8S_TIMEOUT: int = 30

    # ========================================================================
    # Prometheus Settings
    # ========================================================================
    PROMETHEUS_URL: str = "http://localhost:9090"
    PROMETHEUS_TIMEOUT: int = 10

    # ========================================================================
    # Feature Flags
    # ========================================================================
    ENABLE_RAG: bool = True
    ENABLE_K8S_TOOL: bool = True
    ENABLE_SQL_TOOL: bool = True
    ENABLE_METRICS_TOOL: bool = True
    ENABLE_LOG_TOOL: bool = True
    ENABLE_PIPELINE_TOOL: bool = True

    # ========================================================================
    # Logging Settings
    # ========================================================================
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json or text

    class Config:
        """Pydantic config."""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.API_ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.API_ENVIRONMENT == "production"


def get_settings() -> Settings:
    """Get application settings (singleton)."""
    return Settings()


# Global settings instance
settings = get_settings()

# Configure logging level
logging.getLogger().setLevel(getattr(logging, settings.LOG_LEVEL))
