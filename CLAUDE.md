# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI DevOps Assistant: a FastAPI backend where an agent answers DevOps questions by calling tools — SQL queries, Kubernetes state, log analysis, Prometheus metrics, CI pipeline status — plus RAG retrieval over a Chroma vector store. Python 3.11+, fully async (SQLAlchemy async + asyncpg).

The `MCP` project was merged in (see `docs/adr/` for the decisions). It contributed the SQL auto-correction engine
(`tools/sql_correction.py`), the MCP protocol server (`mcp_server/`), and the
document loaders (`rag/loaders.py`). The web chat UI at `/ui` and the streaming
`/chat/stream` endpoint were built during that work.

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

About 500 Python tests plus browser e2e tests (`tests/e2e`, Playwright). `rag/` beyond the document loaders, `services/multi_llm.py`, `observability/`, `ml/`, `evaluation/` and `benchmarking/` have **no tests** — exercise changes there manually.

Do not call `asyncio.run()` inside a test: it closes the event loop that later pytest-asyncio tests reuse, and unrelated tests fail depending on order. Write an `async def` test instead.

`tests/conftest.py:mock_settings` uses keys like `enable_sql`, which do **not** match the real `Settings` field names (`ENABLE_SQL_TOOL`). It cannot be used for monkeypatching as-is.

### Lint / format (what CI enforces)

```bash
ruff check ai_devops_assistant tests
black --check ai_devops_assistant tests
isort --check-only --profile black ai_devops_assistant tests
mypy ai_devops_assistant --ignore-missing-imports --no-strict-optional
pylint ai_devops_assistant --disable=all --enable=E,F --fail-under=9.0
pre-commit run --all-files                         # runs the whole gate, auto-fixes most issues
```

**Always lint with the pinned versions.** CI installs runtime dependencies from the hashed `requirements.lock` (as the Dockerfile does) and tools from `pyproject.toml`'s `[dev]` extra (`ruff==0.1.11`, `black==23.12.1`, `isort==5.13.2`, `mypy==1.7.1`, `pylint==3.0.3`). A newer ruff in a local venv reports ~30 findings CI never sees, which sends you chasing phantoms. If the venv has drifted, build a scratch venv with the pinned versions and lint from that.

Line length is 100 (Black + Ruff). CI (`.github/workflows/ci-cd.yml`) also runs Bandit, Semgrep, Trivy, pip-audit, Helm lint, markdownlint, codespell and typos; `security.yml` (scheduled, currently disabled) adds CodeQL. Workflows trigger on `master`, the default branch.

After changing `requirements.txt`, regenerate the lock:
`pip-compile --generate-hashes --output-file=requirements.lock --strip-extras requirements.txt` (Python 3.11).

All five gates pass with **no exclusions**. JS tests run separately:
`node --test tests/js/*.test.js` (node's built-in runner, zero npm dependencies).
Some tests need a service and skip without one: `TEST_POSTGRES_URL` for the SQL
dialect tests, `TEST_REDIS_URL` for the session-store tests. CI should set both;
locally they skip cleanly.

## Architecture

### Request → agent → tools flow

The core path spans several modules and is the main thing to understand before changing behavior:

1. `main.py` — app factory (`create_app()`), registers routers from `api/routes/` and logging/error middleware from `api/middleware.py`. Lifespan hook initializes the DB (`database/session.py:init_db`) and closes the LLM client on shutdown.
2. `api/routes/chat.py` → `agents/agent.py:get_agent(db_session)`. **`agents/agent.py` is the live agent** used by `/chat`.
3. `_execute_task` runs **a single linear pass**: `_gather_context` (recent messages + RAG + role context) → `_create_execution_plan` (one LLM call returning a JSON step array) → `for step in plan` dispatching tools or reasoning steps → `_generate_final_response`.
4. Tool calls go through `tools/tool_executor.py`: `ToolRegistry` instantiates tools at startup **gated by `ENABLE_*` feature flags in settings**, and `ToolExecutor` dispatches by name. Registered names: `sql_query_tool`, `kubernetes_tool`, `log_analysis_tool`, `metrics_tool`, `pipeline_status_tool`.
5. The SQL and log tools read the request's `AsyncSession` from a ContextVar (`database/context.py`), bound by `api/dependencies.py:get_db_session`.

There is **no re-planning and no reflection**: the plan is generated once and executed straight through. `AgentConfig.max_tool_iterations` caps the tool calls one plan may make; `enable_reflection` is declared but never read.

`/chat` returns the whole answer; `/chat/stream` runs the same pipeline and streams `status`, `plan`, `token` and `done` events as SSE. The web UI in `static/` (plain HTML/CSS/JS, no build step) is mounted at `/ui` and uses the streaming endpoint.

### Tool contract

All tools subclass `tools/base.py:BaseTool`: implement `async execute(**kwargs) -> dict`, override `validate_parameters()` and `get_schema()` (the JSON schema shown to the LLM). Calling a tool goes through `__call__`, which validates and converts exceptions into `{"success": False, "error": ...}` — tools should return `{"success": True, ...}` dicts, not raise.

Adding a tool means editing an if-chain: subclass `BaseTool` → add an `ENABLE_*` field to `Settings` → add a branch in `ToolRegistry._initialize_tools()` → extend `set_session` if it needs a DB session. There is no decorator or plugin registry. `tools/pipeline_tool.py`'s `PipelineProvider` ABC (Azure/Jenkins/GitHub) is the cleanest extension pattern in the repo and a good template.

The SQL tool is deliberately restricted: SELECT-only plus injection-pattern blocking (`tools/sql_tool.py:validate_sql_injection`). Preserve these guards when touching it — blocked unsafe queries are a demoed feature.

### LLM layer

Two competing provider abstractions exist; know which one you're in.

- `services/llm_service.py:get_llm_service()` is **what `/chat` uses**. It dispatches on `settings.LLM_PROVIDER`: `anthropic` → `AnthropicService`, anything else → `OllamaService` (default model `llama3`). Both expose the same `chat`/`generate`/`health_check` surface.
- `services/multi_llm.py` is the richer abstraction (`LLMProvider` ABC, `LLMFactory`, `FallbackLLMClient` with fallback chains) but is used **only** by the CLI and benchmarking, never by the chat path. `services/model_registry.py` — HuggingFace/Ollama model discovery, also CLI-only.
- The two disagree on interface shape: `multi_llm` providers take a prompt string, while the agent calls `chat(messages)`. Consolidating them requires reconciling that first.
- Prompts live under `prompts/` and are versioned/rendered via `agents/prompt_manager.py` (Jinja2) — but the live agent uses the hardcoded `SYSTEM_PROMPT` in `agents/prompts.py`, not PromptManager.

### Configuration

`config/settings.py` is a single pydantic-settings `Settings` class read from env / `.env`. Everything is configured through it: DB URL, LLM provider/URL/model, Chroma dir, Prometheus URL, CI providers (Azure DevOps/Jenkins/GitHub), the `ENABLE_*` tool flags, and observability keys. Add new config there, not as ad-hoc `os.environ` reads.

### Observability

`observability/ai_observability.py` is a homegrown tracing layer (`ObservabilityManager`, `trace_context`, `MetricsCollector`) — not OpenTelemetry. The agent wraps LLM calls and tool executions in it; Prometheus metrics feed Grafana dashboards in `monitoring/grafana/`. When adding agent/tool functionality, keep it traced through this layer.

### Data layer

Async SQLAlchemy models in `database/models.py` (pipeline logs, metric snapshots, chat sessions/messages, RAG docs), common queries in `database/queries.py`. Production uses Postgres via asyncpg; tests use in-memory SQLite — **keep queries compatible with both**, and be wary of dialect-specific SQL: the test suite cannot catch Postgres-only breakage.

## Traps

Verified hazards that cost real debugging time. Check these before changing related code.

- **Per-request state lives in ContextVars.** The agent and tool registry are process-wide singletons, so the DB session is bound per request in `database/context.py` (REST: `api/dependencies.py:get_db_session`; MCP: `mcp_server/adapters.py:build_tool_callable`). Never store a session or per-user state on the agent or a tool.
- **Chat sessions use Redis when `REDIS_URL` is set** (`agents/session_store.py`) and fall back to an in-process dict otherwise — with `WEB_CONCURRENCY>1` that fallback gives each worker its own history.
- **Auth is off when `API_KEY` is unset** (local demo mode). In production `validate_production_security()` refuses to start without `API_KEY`, with the placeholder `SECRET_KEY`, or with `ALLOWED_HOSTS=["*"]`.
- **Broad excepts hide real breakage.** RAG was dead for months because four files had syntax errors and the agent logged "RAG pipeline not available" and carried on. When something is "unavailable", check that it actually imports.
- **Unit-test doubles can lie.** The MCP tests use a fake server, so they cannot catch fastmcp API changes. Start the server and call a tool with a real MCP client after touching `mcp_server/` or upgrading fastmcp.
- **The prompts on disk are not the live prompts.** The agent uses `SYSTEM_PROMPT` in `agents/prompts.py`; `prompts/` and `PromptManager` are not on the request path.

## Repo conventions

- Working rules: understand existing flow before changing it, keep changes small and focused, branch with `git switch -c feature/<name>`, run `pre-commit run --all-files` before pushing, never commit secrets (use `.env` locally; `.env.local` is gitignored).
- Deployment targets: `docker-compose.yml` for local, `infra/kubernetes/` raw manifests + Helm chart in `infra/kubernetes/helm/` (HPA, PDB, NetworkPolicy, ServiceMonitor, ExternalSecrets). CI also exists for Azure Pipelines (`azure-pipelines.yml`) and Jenkins (`Jenkinsfile`).
