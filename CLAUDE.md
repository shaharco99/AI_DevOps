# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI DevOps Assistant: a FastAPI backend where an agent (backed by a local Ollama LLM) answers DevOps questions by calling tools — SQL queries, Kubernetes state, log analysis, Prometheus metrics, CI pipeline status — plus RAG retrieval over a Chroma vector store. Python 3.11+, fully async (SQLAlchemy async + asyncpg).

## Commands

### Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"
cp .env.example .env
```

### Run

```bash
docker-compose up -d                              # full stack: postgres, ollama, backend, prometheus, grafana, redis
uvicorn ai_devops_assistant.main:app --reload     # backend only (needs postgres + ollama running)
./run_demo_checks.sh                              # validate a running deployment end-to-end
```

API at `http://localhost:8000` (`/docs`, `/health`, `/chat`, `/run_sql`, `/analyze_logs`, `/metrics`). Compose maps Ollama to host port 11435 (in-container 11434).

There is also a CLI (`ai-devops`, defined in `cli.py`) for model registry search/install, RAG URL ingestion, and model evaluation.

### Tests

```bash
pytest tests/unit -v                               # unit tests
pytest tests/integration -v                        # integration tests
pytest tests/unit/test_agent.py::test_name -v      # single test
pytest tests/unit --cov=ai_devops_assistant --cov-report=term-missing
```

pytest-asyncio runs in `asyncio_mode = "auto"` — write async tests as plain `async def`, no decorator needed. `tests/conftest.py` provides `test_db_session` (in-memory aiosqlite with all tables created) and `mock_settings`. Markers: `unit`, `integration`, `slow`, `external`.

### Lint / format (what CI enforces)

```bash
ruff check ai_devops_assistant tests
black --check ai_devops_assistant tests
isort --check-only --profile black ai_devops_assistant tests
mypy ai_devops_assistant --ignore-missing-imports --no-strict-optional
pre-commit run --all-files                         # runs the whole gate, auto-fixes most issues
```

Line length is 100 (black + ruff). CI (`.github/workflows/ci-cd.yml`) also runs pylint (errors only, `--fail-under=9.0`), bandit, semgrep, Trivy, pip-audit, markdownlint, and codespell.

## Architecture

### Request → agent → tools flow

The core path spans several modules and is the main thing to understand before changing behavior:

1. `main.py` — app factory (`create_app()`), registers routers from `api/routes/` and logging/error middleware from `api/middleware.py`. Lifespan hook initializes the DB (`database/session.py:init_db`) and closes the Ollama client on shutdown.
2. `api/routes/chat.py` → `agents/agent.py:get_agent(db_session)`. **`agents/agent.py` is the live agent** used by `/chat`; `agents/tool_agent.py` is not referenced by any route.
3. The agent runs a plan → execute-tools → reflect loop (bounded by `AgentConfig.max_tool_iterations`, default 5), optionally prepending RAG context (`use_rag=True` from the chat route).
4. Tool calls go through `tools/tool_executor.py`: `ToolRegistry` instantiates tools at startup **gated by `ENABLE_*` feature flags in settings**, and `ToolExecutor` dispatches by name. Registered names: `sql_query_tool`, `kubernetes_tool`, `log_analysis_tool`, `metrics_tool`, `pipeline_status_tool`.
5. The SQL and log tools need a DB session injected via `ToolRegistry.set_session(session)` — routes pass the request-scoped `AsyncSession` from `api/dependencies.py:get_db_session`.

### Tool contract

All tools subclass `tools/base.py:BaseTool`: implement `async execute(**kwargs) -> dict`, override `validate_parameters()` and `get_schema()` (the JSON schema shown to the LLM). Calling a tool goes through `__call__`, which validates and converts exceptions into `{"success": False, "error": ...}` — tools should return `{"success": True, ...}` dicts, not raise. New tools must be registered in `ToolRegistry._initialize_tools()` behind a settings flag.

The SQL tool is deliberately restricted: SELECT-only plus injection-pattern blocking (`tools/sql_tool.py`). Preserve these guards when touching it — blocked unsafe queries are a demoed feature.

### LLM layer

- `services/llm_service.py` — Ollama client (default model `llama3`), used by the agent.
- `services/multi_llm.py` — provider abstraction (ollama/openai/anthropic) with fallback chains; `services/model_registry.py` — HuggingFace/Ollama model discovery. These are used by the CLI and benchmarking, not the chat path.
- Prompts live under `prompts/` and are versioned/rendered via `agents/prompt_manager.py` (Jinja2); the agent's system prompt is in `agents/prompts.py`.

### Configuration

`config/settings.py` is a single pydantic-settings `Settings` class read from env / `.env`. Everything is configured through it: DB URL, Ollama URL/model, Chroma dir, Prometheus URL, CI providers (Azure DevOps/Jenkins/GitHub), the `ENABLE_*` tool flags, and observability keys. Add new config there, not as ad-hoc `os.environ` reads.

### Observability

`observability/ai_observability.py` is a homegrown tracing layer (`ObservabilityManager`, `trace_context`, `MetricsCollector`) that the agent wraps around LLM calls and tool executions; Prometheus metrics are exposed for Grafana dashboards in `monitoring/grafana/`. When adding agent/tool functionality, keep it traced through this layer.

### Data layer

Async SQLAlchemy models in `database/models.py` (pipeline logs, metric snapshots, chat sessions/messages, RAG docs), common queries in `database/queries.py`. Production uses Postgres via asyncpg; tests use in-memory SQLite — keep queries compatible with both.

## Repo conventions

- The repo's working rules live in `README.md` ("House rules" and "Secrets" sections). Key points: understand existing flow before changing it, keep changes small and focused, branch with `git switch -c feature/<name>`, run `pre-commit run --all-files` before pushing, never commit secrets (use `.env` locally; `.env.local` is gitignored).
- Deployment targets: `docker-compose.yml` for local, `infra/kubernetes/` raw manifests + Helm chart in `infra/kubernetes/helm/`. CI also exists for Azure Pipelines (`azure-pipelines.yml`) and Jenkins (`Jenkinsfile`).
