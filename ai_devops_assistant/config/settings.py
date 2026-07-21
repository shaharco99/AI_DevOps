"""Application settings and configuration management."""

import logging

from pydantic_settings import BaseSettings

# The shipped default. Named so validate_production_security can recognise it
# rather than matching on the literal in two places.
PLACEHOLDER_SECRET_KEY = "your-secret-key-change-this-in-production"


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
    SECRET_KEY: str = PLACEHOLDER_SECRET_KEY
    # "*" keeps K8s probes (which use the pod IP as Host) working in development.
    # Refused in production by validate_production_security(); set it to the real
    # hostnames there and let probes reach the pod by its Service DNS name.
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

    # Conversation memory storage. Empty uses an in-process dict, which is
    # correct for tests and single-process development but loses history across
    # WEB_CONCURRENCY workers and restarts. compose already runs a Redis.
    REDIS_URL: str = ""
    SESSION_STORE_TTL_SECONDS: int = 3600

    # Web UI. Served same-origin from this app, so it needs no CORS entry.
    ENABLE_WEB_UI: bool = True
    # Session cookies are signed and self-contained, so they cannot be revoked
    # before they expire. Keep the lifetime short.
    SESSION_TTL_SECONDS: int = 900  # 15 minutes
    # Set False only for local HTTP development; the cookie is Secure otherwise.
    SESSION_COOKIE_SECURE: bool = True

    # Consumed by docker-compose (Grafana's admin password), not by this app.
    # Declared anyway because .env is shared between the two and Settings forbids
    # unknown keys — without this, the documented `cp .env.example .env` makes the
    # app refuse to start.
    GRAFANA_ADMIN_PASSWORD: str | None = None

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

    # Extra read-only databases the SQL tool can query by name, as JSON:
    #   SQL_SOURCES='{"prod_oracle": "oracle+oracledb_async://u:p@host:1521/?service_name=X",
    #                 "legacy_mssql": "mssql+aioodbc://u:p@host:1433/db?driver=ODBC+Driver+18+for+SQL+Server"}'
    # The driver must be an async one, since the tool runs on the async engine.
    # A JSON string rather than a nested model because it arrives from the
    # environment, where pydantic-settings can only give us a scalar.
    SQL_SOURCES: str = ""
    # Applied per external source. They are someone else's production databases,
    # so the defaults are deliberately smaller and stricter than the app's own.
    SQL_SOURCE_POOL_SIZE: int = 5
    SQL_SOURCE_POOL_TIMEOUT: int = 10
    SQL_SOURCE_CONNECT_TIMEOUT: int = 10

    # ========================================================================
    # LLM Settings
    # ========================================================================
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    # qwen2.5-coder returns valid JSON plans, so _create_execution_plan can parse
    # them and the agent actually calls its tools. llama3 / llama3.1 often answer
    # with prose, planning falls back to "no tools", and the agent then invents
    # data instead of reading it.
    LLM_MODEL: str = "qwen2.5-coder:7b"
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 2048
    LLM_TIMEOUT: int = 60
    LLM_PROVIDER: str = "ollama"
    # Comma-separated model names tried, in order, when the primary model fails.
    # Empty disables the fallback chain. Parsed by llm_service._fallback_models();
    # it is a string rather than a list because it arrives from the environment.
    LLM_FALLBACK_MODELS: str = ""
    OPENAI_API_KEY: str | None = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o"
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

    def production_security_problems(self) -> list[str]:
        """Settings that are unsafe for production, as human-readable problems.

        Returns an empty list outside production. Separated from the raising
        check so tests and a future `--check-config` command can inspect the
        findings without catching an exception.
        """
        if not self.is_production:
            return []

        problems: list[str] = []

        if not self.API_KEY:
            problems.append(
                "API_KEY is not set. Authentication silently becomes a no-op, "
                "leaving every route open."
            )

        if self.SECRET_KEY == PLACEHOLDER_SECRET_KEY:
            problems.append(
                "SECRET_KEY is still the placeholder. It signs session cookies, "
                "so a known value lets anyone mint a valid session."
            )

        if len(self.SECRET_KEY) < 32:
            problems.append("SECRET_KEY is shorter than 32 characters.")

        if "*" in self.ALLOWED_HOSTS:
            problems.append(
                'ALLOWED_HOSTS contains "*", which disables Host header validation '
                "and permits DNS-rebinding and cache-poisoning attacks."
            )

        if not self.SESSION_COOKIE_SECURE:
            problems.append(
                "SESSION_COOKIE_SECURE is false, so session cookies would be sent "
                "over plaintext HTTP."
            )

        if not self.K8S_VERIFY_SSL:
            problems.append(
                "K8S_VERIFY_SSL is false, which disables TLS verification against "
                "the cluster API."
            )

        return problems

    def validate_production_security(self) -> None:
        """Refuse to run with unsafe production settings.

        Fails closed. These used to be warnings that the process logged and then
        carried on past, which meant a missing API_KEY produced one line at
        startup and an unauthenticated deployment thereafter.

        Raises:
            RuntimeError: If any production security setting is unsafe.
        """
        problems = self.production_security_problems()
        if problems:
            raise RuntimeError(
                "Refusing to start: unsafe production configuration.\n"
                + "\n".join(f"  - {problem}" for problem in problems)
            )


def get_settings() -> Settings:
    """Get application settings (singleton)."""
    return Settings()


# Global settings instance
settings = get_settings()

# Configure logging level
logging.getLogger().setLevel(getattr(logging, settings.LOG_LEVEL))
