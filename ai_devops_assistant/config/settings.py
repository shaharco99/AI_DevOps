"""Application settings and configuration management."""

import logging
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings from environment variables."""

    # ========================================================================
    # Application Settings
    # ========================================================================
    APP_NAME: str = "AI DevOps Assistant"
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
    DATABASE_URL: str = "postgresql+asyncpg://devops_user:devops_password@localhost:5432/devops"
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
    LLM_PROVIDER: str = "ollama"
    LLM_FALLBACK_MODELS: str = "mistral,llama3"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    ANTHROPIC_API_KEY: Optional[str] = None
    HUGGINGFACE_API_KEY: Optional[str] = None

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
    EMBEDDING_MODEL: str = "nomic-embed-text"

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
    # CI/CD Pipeline Settings
    # ========================================================================
    # Azure DevOps
    AZURE_DEVOPS_URL: str = "https://dev.azure.com"
    AZURE_DEVOPS_ORG: Optional[str] = None
    AZURE_DEVOPS_PROJECT: Optional[str] = None
    # Jenkins
    JENKINS_URL: str = "http://localhost:8080"
    JENKINS_USER: Optional[str] = None
    # GitHub Actions
    GITHUB_OWNER: Optional[str] = None
    GITHUB_REPO: Optional[str] = None

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
    LOG_INCLUDE_STACKTRACE: bool = True
    DEBUG_LOG_SQL: bool = False

    # ========================================================================
    # AI Observability
    # ========================================================================
    ENABLE_AI_OBSERVABILITY: bool = True
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[str] = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

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
