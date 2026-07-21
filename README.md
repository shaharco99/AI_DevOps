# AI DevOps Assistant 🤖🔧

Imagine a robot friend who looks after your servers.

You ask it *"Why did my build break?"* — and instead of guessing, **it goes and
looks**. It runs a database query, reads your logs, checks Kubernetes, pulls the
graphs. Then it tells you what it found in plain words.

That robot is this project: a FastAPI server with an AI agent inside, a chat
website at `/ui`, and a toolbox the agent can reach into.

---

## Contents

1. [How it works (the big picture)](#how-it-works-the-big-picture)
2. [The robot's toolbox](#the-robots-toolbox)
3. [Demo in 5 minutes](#demo-in-5-minutes)
4. [Demoing the web UI](#demoing-the-web-ui)
5. [Example prompts (per tool)](#example-prompts-per-tool)
6. [Poking the API directly](#poking-the-api-directly)
7. [Which model should I use?](#which-model-should-i-use)
8. [Known rough edges](#known-rough-edges)
9. [Full stack with Docker](#full-stack-with-docker)
10. [Configuration](#configuration)
11. [MCP servers for your editor](#mcp-servers-for-your-editor)
12. [Tests and linting](#tests-and-linting)
13. [Map of the repository](#map-of-the-repository)
14. [License](#license)

---

## How it works (the big picture)

You type a question. Then, in order:

1. **Gather context** — recent messages in your chat, plus anything relevant
   from the knowledge base (RAG).
2. **Make a plan** — one call to the language model, which answers with a small
   JSON list of steps: *"step 1: use the SQL tool"*.
3. **Do the steps** — each step either runs a tool or is a thinking step.
4. **Write the answer** — a final model call turns the collected facts into
   English.

Two honest caveats about that loop:

- It is **one straight pass**. The agent does not re-plan or check itself.
  Whatever the plan says, it does, then it answers.
- Step 2 is where demos live or die. The model must return **valid JSON**. Weak
  models return prose instead, planning silently falls back to "no tools", and
  the answer becomes a confident guess. See
  [Which model should I use?](#which-model-should-i-use) — this matters more
  than anything else on this page.

---

## The robot's toolbox

| Tool name | What it does | On by default? | Needs |
| --- | --- | --- | --- |
| `sql_query_tool` | Runs **SELECT-only** queries, with typo auto-correction | ✅ | the database |
| `log_analysis_tool` | Searches application log **message text** | ✅ | the database |
| `metrics_tool` | Runs PromQL queries | ✅ | Prometheus |
| `pipeline_status_tool` | CI builds — Azure DevOps, Jenkins, GitHub Actions | ✅ | CI credentials |
| `kubernetes_tool` | Lists pods, deployments, services, events | ✅ | a kubeconfig |
| `shell_tool` | A short allow-list of read-only commands | ❌ off | — |

Each has an `ENABLE_*` switch in settings (`ENABLE_SQL_TOOL`,
`ENABLE_SHELL_TOOL`, …).

A tool with no backing service still registers — it just returns an error when
called. On a laptop with no cluster you will see `Failed to initialize
Kubernetes client` in the startup logs. That is expected, and the other tools
work fine.

**The SQL tool is deliberately caged.** SELECT only; `DROP`, `DELETE` and
friends are rejected before they reach the database. Blocking a bad query is a
feature worth demoing, not a bug.

---

## Demo in 5 minutes

No Docker, no Postgres, no Kubernetes. SQLite on disk and a local model.

```bash
# 1) Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2) A model that can actually produce JSON plans (~5GB, one time)
ollama pull qwen2.5-coder:7b

# 3) Give the demo some data to find — without this, everything answers "0"
DATABASE_URL="sqlite+aiosqlite:///./demo.db" python scripts/seed_demo_data.py

# 4) Run it
LLM_PROVIDER=ollama \
LLM_MODEL=qwen2.5-coder:7b \
DATABASE_URL="sqlite+aiosqlite:///./demo.db" \
  uvicorn ai_devops_assistant.main:app --port 8000
```

Open **<http://localhost:8000/ui/>** — the trailing slash matters.

| Address | What's there |
| --- | --- |
| `/ui/` | the chat website |
| `/docs` | interactive API explorer |
| `/health` | liveness check |

Four things that trip people up:

- **`cp .env.example .env` currently stops the app from starting.** The template
  ships `GRAFANA_ADMIN_PASSWORD`, which Docker Compose requires — but `Settings`
  rejects any key it does not declare, so `uvicorn` dies at import with
  `Extra inputs are not permitted`. Until that is fixed, comment the line out of
  `.env` when running the app directly. The compose path needs it, so put it
  back before `docker compose up`.
- The setting is **`LLM_MODEL`**, not `OLLAMA_MODEL`. The wrong name is ignored
  in silence, and you get `model 'llama3' not found`.
- The default model is `llama3`, which you probably have not pulled — and which
  plans badly anyway. Always set `LLM_MODEL` explicitly.
- **Port 8000 is popular.** If something else owns it, use `--port 8011` and
  visit `/ui/` there instead.

The first answer can take 30+ seconds while the model wakes up. After that it is
much faster.

---

## Demoing the web UI

The UI is plain HTML/CSS/JS — no build step, no npm. It lives in
`ai_devops_assistant/static/` and is mounted at `/ui` when `ENABLE_WEB_UI=true`
(the default). It is mounted at `/ui` rather than `/` so it can never shadow an
API route.

A demo script that shows every feature, in an order that builds:

**1. Ask something that needs no tools** — *"What can you help me with?"*
Answers straight away. Establishes that it's a normal chatbot.

**2. Ask something that needs real data** — *"How many pipeline runs failed?
Query the database."* This is the moment worth showing. The status line moves
through **gathering context → planning → responding**, the plan appears, then
the answer streams in word by word. It is reading your seeded rows, not
inventing them.

**3. Show the safety cage** — *"Delete all the pipeline logs."* The SQL tool
refuses anything that isn't a SELECT.

**4. Show the auto-correction** — a nice surprise. When the model invents a
table name like `pipeline_status`, the correction engine maps it to the real
`pipeline_logs` and the query still succeeds. Misspell a column in `/run_sql`
and it replies *"did you mean: level"* along with a schema preview.

**5. Add a document** — the 📎 button uploads a file to the knowledge base
(`/rag/ingest`). It accepts `.pdf`, `.docx`, `.md`, `.txt`, `.csv`, `.xlsx`,
`.pptx`, `.json`, `.yaml`, `.log` and more (`GET /rag/supported-types` lists
them all). Upload a runbook, then ask a question only that runbook answers.

**6. Sessions** — `+` starts a new chat; old ones stay in the left sidebar with
their history. Sessions are kept in Redis when it is configured, so they survive
a restart.

**7. The odds and ends** — a model picker in the top bar (it lists whatever
Ollama has installed), a light/dark toggle, and a **Stop** button that cancels an
answer mid-stream.

Under the hood the UI talks to `POST /chat/stream`, which is Server-Sent Events.
The event types are `status`, `plan`, `token` and `done` — worth opening the
browser Network tab if your audience is technical.

---

## Example prompts (per tool)

Written against the seeded demo data. Phrasing matters: naming the data source
("query the database", "search the logs") pushes the planner toward a tool
instead of answering from memory.

### `sql_query_tool` — the reliable one

- *How many pipeline runs failed? Query the database.*
- *How many rows are in the pipeline_logs table?*
- *Which pipeline has failed the most times?*
- *Show me the 5 most recent pipeline runs and their status.*

To show the cage, then the correction:

- *Delete all the pipeline logs.* → refused, SELECT-only

The auto-correction is easier to show through `/run_sql`, where there is no
model in the way and the result is the same every time:

```bash
# There is no pipeline_status table — it is rewritten to pipeline_logs
curl -s -X POST localhost:8000/run_sql \
  -H 'Content-Type: application/json' \
  -d '{"query":"SELECT COUNT(*) AS n FROM pipeline_status"}'
# -> {"rows":[{"n":20}],"count":1,"execution_time_ms":0.0}
```

Misspell a column name too (drop a letter from `level`) and the reply tells you
which real column you probably meant, with a preview of the schema.

### `log_analysis_tool`

This one searches the **message text**, not the level. Asking for "ERROR
entries" finds nothing, because no message contains the word "ERROR". Ask for
what the message actually *says*:

- *Search the application logs for messages containing redis*
- *Find log messages about slow queries in the last 24 hours*

### `metrics_tool` — needs Prometheus

- *What's the CPU usage of the `api` service right now?*
- *Query Prometheus for the p95 latency over the last hour.*

### `pipeline_status_tool` — needs CI credentials

- *Show me the recent builds from Azure DevOps.*
- *Get the logs for build 1004.*

### `kubernetes_tool` — needs a kubeconfig

- *List all pods in the default namespace.*
- *Give me an overview of the cluster.*
- *Are there any recent warning events in the cluster?*

### RAG — after uploading a document

- *What does the runbook say about restarting the database?*
- *Summarize the document I just uploaded.*

### Multi-tool

- *The nightly-e2e pipeline failed. Check the database for the failure and search*
- *the logs for related errors.*

---

## Poking the API directly

These REST endpoints call the tools straight, with no model in between, so they
always behave the same way. When a demo misbehaves, use them to prove the data
layer is fine and the model is the weak link.

```bash
# Ask a question (full answer, no streaming)
curl -s -X POST localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"How many pipeline runs failed? Query the database."}'

# Watch it think, token by token
curl -N -X POST localhost:8000/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"message":"Why did the nightly-e2e pipeline fail?"}'

# SQL directly — this one is refused
curl -s -X POST localhost:8000/run_sql \
  -H 'Content-Type: application/json' \
  -d '{"query":"DROP TABLE pipeline_logs"}'

# Logs directly — always works, whatever the model does
curl -s -X POST localhost:8000/analyze_logs \
  -H 'Content-Type: application/json' \
  -d '{"query":"redis","time_range_hours":48}'
```

The reply from `/chat` includes a **`tool_calls`** field. That is your honesty
check: if it is `null`, **no tool ran** and the answer came out of the model's
imagination. If it is populated, the numbers are real.

Other endpoints: `/models`, `/rag/ingest`, `/rag/supported-types`,
`/chat/sessions/{id}`, `/metrics`, `/metrics/ai/prometheus`, `/auth/session`,
`/auth/logout`. They are all listed in `/docs`.

---

## Which model should I use?

The planner has to emit valid JSON, and that single requirement decides whether
a demo works. Measured on the prompts above:

| Model | Result |
| --- | --- |
| **`qwen2.5-coder:7b`** | ✅ Calls tools reliably. **Use this for local demos.** |
| **Claude** (`LLM_PROVIDER=anthropic`) | ✅ Best quality — needs `ANTHROPIC_API_KEY` with credit |
| `llama3.1` | ⚠️ Often returns prose instead of JSON — planning fails and it **invents numbers** |
| `llama3` (the default!) | ❌ Usually not installed, and has the same planning weakness |

The `llama3.1` failure mode is the dangerous one, because it does not look like
a failure. Asked how many rows were in an **empty** table, it answered
*"**105,678**"* — fluent, well formatted and entirely fictional. The logs showed
`Planning failed, using simple approach`, and `tool_calls` came back `null`.

Never demo on a model you have not checked `tool_calls` for.

To use Claude instead:

```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-opus-4-8
```

Same agent, same tools, different brain. Switch back with
`LLM_PROVIDER=ollama`.

---

## Known rough edges

An honest list — all of these are reachable during a demo.

- **The stock `.env` template will not boot the app.** `Settings` declares no
  `extra` policy, so pydantic-settings defaults to forbidding unknown keys, and
  the `GRAFANA_ADMIN_PASSWORD` that `.env.example` and Docker Compose both need
  crashes the process at import. Either declare it on `Settings` or set
  `extra = "ignore"` on its `Config` — declaring it is safer, since ignoring
  silently swallows typos in real setting names.
- **The planner can crash the endpoint.** If the model emits tool parameters as
  a list (`["list_pods", "-n", "default"]`) instead of an object, `/chat`
  returns **500** with a Pydantic validation error. Seen with `llama3.1` on
  Kubernetes questions.
- **No re-planning.** One plan, executed straight through.
  `max_tool_iterations` and `enable_reflection` exist in the config but **are
  never read** — they constrain nothing.
- **Empty tables answer "0".** Truthful, but it looks broken. Run the seed
  script.
- **Two LLM abstractions.** `services/llm_service.py` is what `/chat` uses;
  `services/multi_llm.py`, with its fallback chains, is used **only** by the CLI
  and benchmarking. Don't confuse them.
- **The prompts on disk are not the live prompts.** `prompts/` and
  `PromptManager` exist, but the running agent uses the hardcoded
  `SYSTEM_PROMPT` in `agents/prompts.py`.
- **Thin test coverage.** `rag/`, `observability/`, `ml/`, `evaluation/` and
  `benchmarking/` have no tests at all. Exercise changes there by hand.

---

## Full stack with Docker

```bash
cp .env.example .env
docker compose up -d
```

That brings up Postgres, Ollama, the backend, the MCP protocol server,
Prometheus, Grafana and Redis.

| Service | Address | Note |
| --- | --- | --- |
| Backend + UI | `localhost:8000` | UI at `/ui/` |
| MCP server | `127.0.0.1:8001` | |
| Grafana | `127.0.0.1:3000` | dashboards (admin / admin) |
| Prometheus | `127.0.0.1:9090` | |
| Postgres | `127.0.0.1:5432` | |
| Redis | `127.0.0.1:6379` | chat sessions |
| Ollama | `localhost:11435` | **11435** on the host, 11434 inside |

Everything except the backend binds to `127.0.0.1`, so it is not reachable from
the network.

### If 8000 or 3000 is already taken

Compose **merges** port lists rather than replacing them, so an override that
adds `8080:8000` leaves `8000` published too and the clash remains. The
`!override` tag is what actually replaces the list. Put this in
`docker-compose.override.yml` (gitignored):

```yaml
services:
  backend:
    ports: !override
      - "8080:8000"
  grafana:
    ports: !override
      - "127.0.0.1:3001:3000"
```

With that override in place the addresses become:

| Service | Address |
| --- | --- |
| **Chat UI** | **<http://localhost:8080/ui/>** |
| API docs | <http://localhost:8080/docs> |
| Grafana | <http://localhost:3001> (admin / admin) |
| Prometheus | <http://localhost:9090> |
| MCP server | <http://localhost:8001> |

Then pull a model and seed data *inside* the stack:

```bash
docker compose exec ollama ollama pull qwen2.5-coder:7b
docker compose exec ollama ollama pull nomic-embed-text     # for RAG
# PYTHONPATH is needed because running `python scripts/x.py` puts scripts/ on
# the import path instead of /app, so the package is not importable.
docker compose exec -e PYTHONPATH=/app backend python scripts/seed_demo_data.py
```

To validate a running deployment end to end: `./run_demo_checks.sh`.
Kubernetes manifests and Helm charts live in `infra/kubernetes/`.

---

## Configuration

Everything is one pydantic-settings class — `config/settings.py` — read from the
environment or `.env`. Add new settings there, never as ad-hoc `os.environ`
reads. Start with `cp .env.example .env`.

| Setting | Default | What it does |
| --- | --- | --- |
| `LLM_PROVIDER` | `ollama` | `ollama` or `anthropic` |
| `LLM_MODEL` | `llama3` | **Override this.** Not `OLLAMA_MODEL` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | 11435 from the host under compose |
| `ANTHROPIC_API_KEY` | — | required when the provider is `anthropic` |
| `DATABASE_URL` | Postgres | SQLite works fine for demos |
| `ENABLE_WEB_UI` | `true` | serves `/ui` |
| `ENABLE_RAG` | `true` | knowledge base |
| `ENABLE_SQL_TOOL` | `true` | one flag per tool — see `config/settings.py` |
| `ENABLE_SHELL_TOOL` | `false` | leave it off unless you mean it |

Secrets belong in `.env` (git-ignored) or a secret manager — never in code.
Gitleaks, detect-secrets and Talisman run in pre-commit to enforce that.

---

## MCP servers for your editor

`.mcp.json` wires four MCP servers into MCP-aware editors (Claude Code, Cursor,
VS Code). These are for *you*, working on the repo — they are not part of the
running application. Approve them once when your editor prompts.

| Server | Gives the assistant | Needs |
| --- | --- | --- |
| `kubernetes` | pods, logs, events, Helm releases via `kubectl` | a cluster — `minikube start` |
| `prometheus` | PromQL queries, metric discovery, scrape targets | `docker compose up -d prometheus` |
| `postgres` | schema, `EXPLAIN` plans, index and health analysis | `docker compose up -d postgres` |
| `ai-devops` | this project's own tools over MCP | `docker compose up -d mcp-server` |

Two deliberate choices, both about blast radius:

- **The Kubernetes server runs with `ALLOW_ONLY_NON_DESTRUCTIVE_TOOLS=true`.** No
  `kubectl_delete`, no `uninstall_helm_chart`. Scale, apply and patch stay available.
- **The Postgres server runs with `--access-mode=restricted`** — read-only, with
  query timeouts. Its default is unrestricted arbitrary SQL, which is not what you
  want an agent holding.

Versions are pinned, and every credential is a `${VAR}` reference resolved from
your environment or `.env` — the file is committed, so no literals. The two
containerised servers join the compose network (`ai-devops_devops`) and reach
Postgres and Prometheus by service name.

There is no Docker MCP server here on purpose. Docker's official catalog does not
ship one — `docker mcp gateway` hosts other catalog servers, it does not manage
containers — and the third-party packages claiming to fill the gap are unaudited
and hold root-equivalent access to your daemon. Use `docker compose` in a shell.

---

## Tests and linting

```bash
pytest tests/unit -v
pytest tests/integration -v
node --test tests/js/*.test.js          # UI tests, no npm needed
```

`pytest-asyncio` runs in auto mode — write `async def` tests with no decorator.
Some tests skip without `TEST_POSTGRES_URL` / `TEST_REDIS_URL`.

```bash
pre-commit run --all-files              # the whole gate
```

**Use the pinned versions** from `pyproject.toml`'s `[dev]` extra —
`ruff==0.1.11`, `black==23.12.1`, `isort==5.13.2`, `mypy==1.7.1`,
`pylint==3.0.3`. A newer local Ruff reports ~30 findings CI never sees and sends
you chasing ghosts. Line length is 100.

---

## Map of the repository

```text
ai_devops_assistant/
  main.py            app factory; mounts /ui
  agents/agent.py    the live agent — context → plan → tools → answer
  api/routes/        chat, run_sql, analyze_logs, metrics, rag, auth, models, health
  tools/             the toolbox + sql_correction.py (typo fixing)
  services/          llm_service.py (live) · multi_llm.py (CLI only)
  rag/               vector store, document loaders
  mcp_server/        MCP protocol server
  database/          async SQLAlchemy models and queries
  static/            the web UI — plain HTML/CSS/JS
  config/settings.py every setting lives here
scripts/             seed_demo_data.py
infra/               Docker, Helm, Kubernetes
docs/adr/            architecture decisions
```

## License

MIT — see the LICENSE file.
