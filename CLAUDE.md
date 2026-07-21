# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI DevOps Assistant: a FastAPI backend where an agent answers DevOps questions by calling tools — SQL queries, Kubernetes state, log analysis, Prometheus metrics, CI pipeline status — plus RAG retrieval over a Chroma vector store. Python 3.11+, fully async (SQLAlchemy async + asyncpg).

The `MCP` project was merged in (see `MERGE_PROGRESS.md` for the record and
`docs/adr/` for the decisions). It contributed the SQL auto-correction engine
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

Coverage is thin (~660 test lines against ~10.6k source lines) and concentrated in API/tools. `rag/`, `services/multi_llm.py`, `observability/`, `ml/`, `evaluation/`, and `benchmarking/` have **no tests at all** — changes there are unguarded, so exercise them manually.

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

**Always lint with the pinned versions.** CI installs from `pyproject.toml`'s `[dev]` extra (`ruff==0.1.11`, `black==23.12.1`, `isort==5.13.2`, `mypy==1.7.1`, `pylint==3.0.3`). A newer ruff in a local venv reports ~30 findings CI never sees, which sends you chasing phantoms. If the venv has drifted, build a scratch venv with the pinned versions and lint from that.

Line length is 100 (Black + Ruff). CI (`.github/workflows/ci-cd.yml`) also runs bandit, semgrep, Trivy, CodeQL, pip-audit, markdownlint, and codespell.

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
5. The SQL and log tools need a DB session injected via `ToolRegistry.set_session(session)` — routes pass the request-scoped `AsyncSession` from `api/dependencies.py:get_db_session`.

There is **no re-planning and no reflection**: the plan is generated once and executed straight through. `AgentConfig.max_tool_iterations` and `enable_reflection` are declared but never read anywhere in the codebase — nothing bounds the loop except plan length. Don't trust those fields to constrain behavior.

`/chat` is request/response only. No SSE, no WebSocket, and **no frontend of any kind exists** — no static assets, no templates, no HTML/JS/CSS anywhere. `stream_generate`/`stream_chat` exist on the LLM services but are not surfaced over HTTP. (Phase 2 of the merge adds both.)

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

- **`get_agent()` binds one session forever.** `agents/agent.py:get_agent()` caches a module-global agent and binds the *first* request's `AsyncSession` into it. Later requests reuse a stale, likely-closed session. Worse, concurrent requests share one agent *and* one `conversation_memory` — that's conversation bleed between users, not just a stale handle. Don't add per-user state to the agent object.
- **Session memory is in-process.** `agents/memory.py:SessionManager` is a plain dict, lost on restart and not shared across workers. The Dockerfile encourages `WEB_CONCURRENCY>1`, under which a user's turns hit different workers and see different histories. Durable history is separate, in Postgres via `database/queries.py:add_chat_message`.
- **Redis is running and completely unused.** It's in `docker-compose.yml` with a healthcheck and volume, and nothing in the Python code connects to it. It's the intended home for shared sessions and a distributed rate limiter.
- **Auth silently disappears.** `api/auth.py` is a single static `X-API-Key`. If `settings.API_KEY` is unset, `require_api_key` becomes a no-op and only logs a warning — it does not fail closed. `/metrics` and `/metrics/ai/*` have no auth dependency at all (`main.py` omits `dependencies=auth_deps` for that router only). `SECRET_KEY` ships with a placeholder default and `ALLOWED_HOSTS` defaults to `["*"]`.
- **Broad excepts hide real breakage.** RAG was entirely dead for months — four files had syntax errors, so `import ai_devops_assistant.rag` raised and the agent logged "RAG pipeline not available" and carried on. Tests never noticed because they never import RAG. When something is mysteriously "unavailable", check that it actually imports before believing the log line.
- **`rag/vector_store.py` may still be broken.** It initializes Chroma with `chroma_db_impl="duckdb+parquet"`, a settings key removed in chromadb 0.4.x — and `chromadb==0.4.22` is pinned. This was masked by the import failure above and is still unverified.
- **Known dead code** (don't build on it): `agents/tool_agent.py` (361 lines, zero references anywhere, and passes capabilities as strings where the agent compares enum members); `ToolExecutor.execute_rag_retrieval` (its `rag_retriever` is hardcoded `None`, so it always returns failure); `agent.py:_retrieve_rag_context` and several sibling helpers left from an earlier single-shot design.

## Repo conventions

- The repo's working rules live in `README.md` ("House rules" and "Secrets" sections). Key points: understand existing flow before changing it, keep changes small and focused, branch with `git switch -c feature/<name>`, run `pre-commit run --all-files` before pushing, never commit secrets (use `.env` locally; `.env.local` is gitignored).
- Deployment targets: `docker-compose.yml` for local, `infra/kubernetes/` raw manifests + Helm chart in `infra/kubernetes/helm/` (HPA, PDB, NetworkPolicy, ServiceMonitor, ExternalSecrets). CI also exists for Azure Pipelines (`azure-pipelines.yml`) and Jenkins (`Jenkinsfile`).
- While the merge is active, update `MERGE_PROGRESS.md` at the end of each session: current phase, next action, one Log line, and any deviation from the plan under Decisions.
