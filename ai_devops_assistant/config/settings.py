"""Application settings and configuration management."""

import logging

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
    # "*" keeps K8s probes (which use the pod IP as Host) working; restrict in production
    ALLOWED_HOSTS: list[str] = ["*"]
    # Empty API_KEY disables auth (local demo); set it to require X-API-Key on API routes
    API_KEY: str | None = None
    CORS_ORIGINS: list[str] = []
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_CHAT: str = "30/minute"
    RATE_LIMIT_SQL: str = "60/minute"

    # MCP protocol server. Runs as a separate process from the same image, so it
    # binds its own port — 8000 is uvicorn's.
    MCP_HOST: str = "0.0.0.0"
    MCP_PORT: int = 8001
    # Required in production: the MCP transport exposes tool execution, so an
    # unauthenticated listener is a remote administrative interface.
    MCP_AUTH_TOKEN: str | None = None

    # Shell tool. Off by default — it runs processes on the host, and nothing it
    # offers is unavailable through the Kubernetes and SQL tools.
    ENABLE_SHELL_TOOL: bool = False

    # Web UI. Served same-origin from this app, so it needs no CORS entry.
    ENABLE_WEB_UI: bool = True
    # Session cookies are signed and self-contained, so they cannot be revoked
    # before they expire. Keep the lifetime short.
    SESSION_TTL_SECONDS: int = 900  # 15 minutes
    # Set False only for local HTTP development; the cookie is Secure otherwise.
    SESSION_COOKIE_SECURE: bool = True

    # ========================================================================
    # Database Settings
    # ========================================================================
    DATABASE_URL: str = "postgresql+asyncpg://devops_user:devops_password@localhost:5432/devops"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 40
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_POOL_RECYCLE: int = 1800
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
    OPENAI_API_KEY: str | None = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL: str = "claude-opus-4-8"
    # Claude output cap includes thinking tokens; keep generous headroom
    ANTHROPIC_MAX_TOKENS: int = 16000
    HUGGINGFACE_API_KEY: str | None = None

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
    KUBECONFIG: str | None = None
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
    AZURE_DEVOPS_ORG: str | None = None
    AZURE_DEVOPS_PROJECT: str | None = None
    # Jenkins
    JENKINS_URL: str = "http://localhost:8080"
    JENKINS_USER: str | None = None
    # GitHub Actions
    GITHUB_OWNER: str | None = None
    GITHUB_REPO: str | None = None

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
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
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
