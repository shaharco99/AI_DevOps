# AI DevOps Assistant 🤖🔧

Imagine you have a very smart robot friend who takes care of your servers.
You can ask it things like *"Why did my build break?"* or *"Which service is slow?"*
— and instead of guessing, the robot **goes and looks**: it reads logs, checks the
database, peeks at Kubernetes, and looks at the graphs. Then it explains what it
found in plain words.

That robot is this project.

---

## Table of Contents

1. [What is this?](#what-is-this)
2. [How does it work? (the big picture)](#how-does-it-work-the-big-picture)
3. [What's in the box?](#whats-in-the-box)
4. [The robot's toolbox](#the-robots-toolbox)
5. [Quick start (the magic button)](#quick-start-the-magic-button)
6. [Want the robot to use Claude?](#want-the-robot-to-use-claude)
7. [Talking to the robot (API examples)](#talking-to-the-robot-api-examples)
8. [Running it on your own computer](#running-it-on-your-own-computer)
9. [Tests](#tests)
10. [Keeping the code clean and safe](#keeping-the-code-clean-and-safe)
11. [Deploying to Kubernetes](#deploying-to-kubernetes)
12. [Secrets (the keys to your house)](#secrets-the-keys-to-your-house)
13. [Configuration cheat sheet](#configuration-cheat-sheet)
14. [Map of the repository](#map-of-the-repository)
15. [When things go wrong](#when-things-go-wrong)
16. [House rules (for humans and robots)](#house-rules-for-humans-and-robots)
17. [License](#license)

---

## What is this?

A **FastAPI** web server with an **AI agent** inside. The agent is powered by a
large language model — a local one (**Ollama** with `llama3`) or a cloud one
(**Anthropic Claude**). When you ask a question, the agent doesn't just answer
from memory: it picks the right **tool**, uses it to fetch real data, and only
then writes its answer.

It also has a **bookshelf** (a RAG system built on the Chroma vector database):
you can feed it documentation and runbooks, and it will look things up when it
answers you.

Everything is **async Python 3.11+** (FastAPI, SQLAlchemy async, asyncpg), and
the whole platform is watched by **Prometheus** and drawn in pretty pictures by
**Grafana**.

---

## How does it work? (the big picture)

Think of it like ordering food:

1. **You ask a question** → the waiter (FastAPI) takes your order at `/chat`.
2. **The chef (the agent) thinks** → "to answer this, I need to check the logs
   and the metrics."
3. **The chef uses kitchen tools** → SQL queries, Kubernetes lookups, log
   search, Prometheus queries, CI pipeline status.
4. **The chef tastes and thinks again** → the agent runs a *plan → use tools →
   reflect* loop (up to 5 rounds) until it's happy with the answer.
5. **You get your dish** → a clear answer, plus a list of which tools were used
   and what they returned.

```mermaid
flowchart TD
    U[You / API Client] --> |HTTP| API[FastAPI Backend]
    API --> |/chat| AGENT[AI Agent - plan, use tools, reflect]
    AGENT --> SQL[SQL Tool]
    AGENT --> K8S[Kubernetes Tool]
    AGENT --> LOGS[Log Analysis Tool]
    AGENT --> METRICS[Metrics Tool]
    AGENT --> PIPE[Pipeline Status Tool]
    AGENT --> RAG[RAG Retrieval]

    RAG --> CHROMA[(Chroma Vector Store)]
    SQL --> POSTGRES[(PostgreSQL)]
    LOGS --> POSTGRES
    METRICS --> PROM[Prometheus]
    K8S --> CLUSTER[Kubernetes API]
    PIPE --> CI[Azure DevOps / Jenkins / GitHub]
    AGENT --> LLM[Ollama or Anthropic Claude]
    PROM --> GRAFANA[Grafana Dashboards]
```

Every LLM call and tool run is traced by a homegrown observability layer
(`observability/ai_observability.py`) and exported as Prometheus metrics, so you
can *see* what the robot is doing on the Grafana dashboards.

---

## What's in the box?

`docker compose up -d` starts a small city of containers:

| Container | What it is (like you're five) | Where to find it |
| --- | --- | --- |
| `ai-devops-backend` | The robot's brain and mouth (FastAPI + agent) | <http://localhost:8000> |
| `ai-devops-postgres` | A big filing cabinet for logs and chats | `localhost:5432` (user `devops_user`, db `devops`) |
| `ai-devops-ollama` | A talking parrot on your computer (the local LLM) | `localhost:11435` (in-container `11434`) |
| `ai-devops-prometheus` | A nurse that takes everyone's temperature every few seconds | <http://localhost:9090> |
| `ai-devops-grafana` | Pretty pictures of all those temperatures | <http://localhost:3000> (admin / admin) |
| `ai-devops-redis` | A tiny notepad for remembering things quickly (optional cache) | `localhost:6379` |

The Chroma vector store (the bookshelf) lives inside the backend as an embedded
database, persisted in the `chroma_data` volume.

---

## The robot's toolbox

Each tool is a Python class under `ai_devops_assistant/tools/`. They all follow
one simple contract: implement `async execute(**kwargs) -> dict`, return
`{"success": True, ...}` — never raise at the caller. Tools are registered in
`tools/tool_executor.py` and each one can be switched on/off with an
`ENABLE_*` flag in your `.env`:

| Tool name | What it does | Flag |
| --- | --- | --- |
| `sql_query_tool` | Runs **read-only** SQL against PostgreSQL, with guardrails | `ENABLE_SQL_TOOL` |
| `kubernetes_tool` | Looks at pods, services, and events in your cluster | `ENABLE_K8S_TOOL` |
| `log_analysis_tool` | Searches and summarizes application logs from the database | `ENABLE_LOG_TOOL` |
| `metrics_tool` | Asks Prometheus questions (PromQL) | `ENABLE_METRICS_TOOL` |
| `pipeline_status_tool` | Checks CI/CD builds in Azure DevOps, Jenkins, or GitHub | `ENABLE_PIPELINE_TOOL` |

About those SQL guardrails: the tool refuses anything scary. `DROP`, `DELETE`,
`INSERT`, `UPDATE`, SQL comments, and injection patterns are all blocked before
the query ever runs — using word-boundary matching, so innocent columns like
`created_at` are fine. Blocked queries are a feature, not a bug (try one in the
[API examples](#talking-to-the-robot-api-examples)).

RAG retrieval (`ENABLE_RAG`) is not a tool the agent picks — relevant documents
are fetched from Chroma and given to the agent as extra context before it
answers.

**Adding a new tool:** subclass `tools/base.py:BaseTool`, implement
`execute()`, `validate_parameters()`, and `get_schema()` (the JSON schema the
LLM sees), then register it in `ToolRegistry._initialize_tools()` behind a new
settings flag.

---

## Quick start (the magic button)

You need: **Docker + Docker Compose**. That's it for this path.

```bash
# 1) Get the code
git clone https://github.com/yourusername/ai-devops-assistant.git
cd ai-devops-assistant

# 2) Make your own settings file (safe template, no secrets inside)
cp .env.example .env

# 3) Press the magic button
docker compose up -d

# 4) Teach the parrot to talk (download the models, first time only)
docker exec ai-devops-ollama ollama pull llama3
docker exec ai-devops-ollama ollama pull nomic-embed-text

# 5) Say hello
curl -s http://localhost:8000/health
```

Then open:

- **API playground**: <http://localhost:8000/docs>
- **Grafana**: <http://localhost:3000> (admin / admin)
- **Prometheus**: <http://localhost:9090>

To check the whole deployment end-to-end (containers, health, chat, logs,
metrics, unit tests) run the demo script:

```bash
./run_demo_checks.sh        # or: python demo_checks.py
```

> The first `/chat` call can take 30+ seconds — the model is waking up.
> After that it's much faster.

---

## Want the robot to use Claude?

By default the robot thinks with local Ollama (free, private, needs no key).
If you want a much smarter cloud brain, plug in **Anthropic Claude**:

```bash
# in your .env
LLM_PROVIDER="anthropic"
ANTHROPIC_API_KEY="sk-ant-..."          # get one at console.anthropic.com
ANTHROPIC_MODEL="claude-opus-4-8"       # the default; change if you like
ANTHROPIC_MAX_TOKENS=16000
```

Restart, and that's it — the same agent, the same tools, a different brain.
It uses the official `anthropic` SDK (`services/anthropic_service.py`) with
adaptive thinking enabled, and the traces/metrics automatically report the real
provider and model. Switch back anytime with `LLM_PROVIDER="ollama"`.

With Docker Compose, `LLM_PROVIDER`, `ANTHROPIC_API_KEY`, and `ANTHROPIC_MODEL`
are passed straight from your `.env` into the backend container.

There is also a wider multi-provider layer (`services/multi_llm.py`, used by
the `ai-devops` CLI and benchmarking) that supports Ollama, OpenAI, and
Anthropic with fallback chains.

---

## Talking to the robot (API examples)

### Ask a question

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Why did my pipeline fail?"}'

curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Which service has the highest latency?"}'
```

### Run safe SQL

```bash
# A nice query — allowed
curl -X POST http://localhost:8000/run_sql \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT * FROM application_logs LIMIT 5"}'

# A naughty query — blocked on purpose (this is a feature!)
curl -X POST http://localhost:8000/run_sql \
  -H "Content-Type: application/json" \
  -d '{"query": "DROP TABLE application_logs"}'
```

### Search logs and query metrics

```bash
curl -X POST http://localhost:8000/analyze_logs \
  -H "Content-Type: application/json" \
  -d '{"query": "ERROR", "time_range_hours": 24, "limit": 50}'

curl -X POST http://localhost:8000/metrics \
  -H "Content-Type: application/json" \
  -d '{"query": "histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))"}'
```

### Health

```bash
curl http://localhost:8000/health
```

### How "Why did my pipeline fail?" actually works

1. The agent reads your question and decides it needs `pipeline_status_tool`.
2. The tool calls the Azure DevOps REST API (or Jenkins/GitHub) with your token.
3. It gets back real build results: what failed, when, on which branch.
4. The LLM turns that into a human answer: *"Run #2024.04.23.1 failed in the
   Unit Tests stage — a database connection timeout in `test_api.py`. Try…"*

For that to work, give the robot a key to your CI system in `.env`:

```bash
AZURE_DEVOPS_URL=https://dev.azure.com
AZURE_DEVOPS_ORG=your-organization
AZURE_DEVOPS_PROJECT=your-project
AZURE_DEVOPS_PAT=your-personal-access-token   # needs Build (Read) scope
```

---

## Running it on your own computer

For development you run the backend directly and keep only Postgres + Ollama in
Docker:

```bash
# One-time setup
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install -e ".[dev]"
pre-commit install
cp .env.example .env

# Start just the helpers
docker compose up -d postgres ollama

# Start the backend with auto-reload
uvicorn ai_devops_assistant.main:app --reload
```

There is also a CLI, installed as `ai-devops` (see `cli.py`), for searching and
installing models from the HuggingFace/Ollama registries, ingesting URLs into
the RAG bookshelf, and evaluating models.

---

## Tests

```bash
pytest tests/unit -v                    # fast unit tests
pytest tests/integration -v             # API integration tests
pytest tests/unit/test_agent.py::test_name -v          # one single test
pytest tests/unit --cov=ai_devops_assistant --cov-report=term-missing
```

Good to know:

- pytest-asyncio runs in `asyncio_mode = "auto"` — write async tests as plain
  `async def`, no decorator needed.
- `tests/conftest.py` gives you `test_db_session` (an in-memory SQLite database
  with all tables already created) and `mock_settings`.
- Tests use SQLite, production uses PostgreSQL — keep queries friendly to both.
- Markers: `unit`, `integration`, `slow`, `external`.

---

## Keeping the code clean and safe

Before every push, one command tidies almost everything for you:

```bash
pre-commit run --all-files
```

What the robots check (locally and in CI, `.github/workflows/ci-cd.yml`):

| Check | Tool | What it catches |
| --- | --- | --- |
| Linting | Ruff (+ Pylint in CI) | bugs, style, unused imports |
| Formatting | Black + isort (line length 100) | messy code, messy imports |
| Types | MyPy | wrong types |
| Code security (SAST) | Bandit + Semgrep | hardcoded secrets, unsafe patterns |
| Dependency safety (SCA) | pip-audit | known CVEs in packages |
| Container safety | Trivy | vulnerable Docker images |
| Docs | markdownlint + codespell | broken markdown, typos |

Run any of them by hand:

```bash
ruff check ai_devops_assistant tests
black --check ai_devops_assistant tests
isort --check-only --profile black ai_devops_assistant tests
mypy ai_devops_assistant --ignore-missing-imports --no-strict-optional
bandit -r ai_devops_assistant/
pip-audit -r requirements.txt
```

CI/CD also exists for **Azure Pipelines** (`azure-pipelines.yml`) and
**Jenkins** (`Jenkinsfile`), and GitHub Actions builds/publishes the Docker
image and runs scheduled security scans.

---

## Deploying to Kubernetes

Docker Compose is your toy box at home. Kubernetes is the big playground.
You can deploy either with raw manifests (`kubectl`) or with the Helm chart.

### Option 1 — Helm (recommended)

Helm is like a recipe book: one command cooks the whole meal, and if the meal
burns, it puts everything back the way it was.

```bash
# Add chart repositories (first time)
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add otwld https://otwld.github.io/ollama-helm/
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# The safe way: the deploy script lints, dry-renders, deploys with
# --rollback-on-failure --wait, and prints diagnostics if anything breaks
./infra/kubernetes/helm/deploy.sh ai-devops-assistant ai-devops-assistant values.yaml

# Dry run (see what would happen without doing it)
DRY_RUN=true ./infra/kubernetes/helm/deploy.sh

# Production values (security-hardened: external secrets, TLS, non-root,
# network policies, HPA, PDB)
./infra/kubernetes/helm/deploy.sh prod-release prod-namespace values-production.yaml
```

Useful Helm commands:

```bash
helm status ai-devops-assistant -n ai-devops-assistant
helm history ai-devops-assistant -n ai-devops-assistant
helm rollback ai-devops-assistant 1          # go back to the previous version
helm uninstall ai-devops-assistant           # remove everything
```

### Option 2 — plain kubectl

```bash
kubectl apply -f infra/kubernetes/namespace.yaml
kubectl apply -f infra/kubernetes/

kubectl get pods -n ai-devops-assistant
kubectl rollout status deploy/ai-devops-assistant -n ai-devops-assistant

# Make sure the in-cluster Ollama has a model
OLLAMA_POD=$(kubectl get pod -n ai-devops-assistant -l app=ollama -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n ai-devops-assistant "$OLLAMA_POD" -- ollama pull llama3

# Reach the API from your machine
kubectl port-forward svc/ai-devops-assistant 8000:80 -n ai-devops-assistant
curl -s http://localhost:8000/health
```

Local playground: `minikube start --cpus=4 --memory=8192` first, then the same
commands.

Debugging on the cluster:

```bash
kubectl logs -n ai-devops-assistant deployment/ai-devops-assistant -f
kubectl describe pod <pod-name> -n ai-devops-assistant
kubectl get events -n ai-devops-assistant --sort-by='.lastTimestamp'
kubectl top pods -n ai-devops-assistant
```

Cleanup: `kubectl delete namespace ai-devops-assistant` (this deletes data
volumes too — be sure).

---

## Secrets (the keys to your house)

Passwords, API keys, and tokens are like your house keys. You never tape your
house key to a postcard and mail it to everyone — and you never commit secrets
to git. **Even in a private repo. Even "just for a second."**

### The rules

1. Real secrets live in `.env` or `.env.local` — both are in `.gitignore`.
2. `.env.example` and `.env.local.example` are safe templates: names, no values.
3. Generate a strong app key:
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`
4. Rotate keys regularly, and immediately when someone leaves or something leaks.

### What needs protecting here

`SECRET_KEY`, `DATABASE_URL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`AZURE_DEVOPS_PAT`, `JENKINS_API_TOKEN`, `GITHUB_TOKEN`.

### Where secrets live in each environment

| Environment | Use this | Effort |
| --- | --- | --- |
| Local development | `.env.local` file (gitignored) | ⭐ easy |
| Docker Compose | `.env` / `.env.local`, or a gitignored `.secrets/` dir with compose `secrets:` | ⭐ easy |
| CI/CD | Platform secrets (GitHub Actions `secrets.*`, Azure variable groups, Jenkins credentials) | ⭐ easy |
| Staging | Sealed Secrets (encrypted secrets you *can* commit) or External Secrets Operator | ⭐⭐ medium |
| Production | External Secrets Operator (AWS Secrets Manager / Azure Key Vault / Vault) | ⭐⭐⭐ serious |

For Kubernetes there are ready-made pieces in `infra/kubernetes/`:
`setup-secrets.sh` (creates the `ai-devops-secrets` Secret for you) and
`external-secrets-config.yaml` (External Secrets Operator examples). The Helm
chart supports built-in secrets, existing secrets, and ESO.

Quick checks:

```bash
kubectl get secret ai-devops-secrets -n ai-devops-assistant
kubectl describe secret ai-devops-secrets -n ai-devops-assistant   # keys only, no values
python -c "import os; print(os.getenv('SECRET_KEY') and 'set' or 'NOT SET')"
```

### 🚨 "Help, I committed a secret!"

1. **Rotate it right now** in the system that issued it — the old value is
   burned forever, deleting the commit does not un-leak it.
2. Then scrub git history (BFG Repo-Cleaner or `git filter-repo`).

---

## Configuration cheat sheet

Everything is configured through one pydantic-settings class
(`ai_devops_assistant/config/settings.py`), which reads your environment and
`.env`. Add new settings there — never as ad-hoc `os.environ` reads. The most
useful knobs:

```bash
# Who does the thinking
LLM_PROVIDER="ollama"                    # ollama | anthropic
LLM_MODEL=llama3                         # Ollama model
OLLAMA_BASE_URL=http://localhost:11434   # compose maps host port 11435 → 11434
ANTHROPIC_API_KEY=""                     # for Claude
ANTHROPIC_MODEL="claude-opus-4-8"
ANTHROPIC_MAX_TOKENS=16000

# The filing cabinet
DATABASE_URL=postgresql+asyncpg://devops_user:devops_password@localhost:5432/devops

# The bookshelf (RAG)
CHROMA_PERSIST_DIR=/data/chroma
EMBEDDING_MODEL="nomic-embed-text"
RAG_CHUNK_SIZE=1000
RAG_CHUNK_OVERLAP=100

# The nurse
PROMETHEUS_URL=http://localhost:9090

# Which tools the robot may use
ENABLE_RAG=true
ENABLE_SQL_TOOL=true
ENABLE_K8S_TOOL=true
ENABLE_LOG_TOOL=true
ENABLE_METRICS_TOOL=true
ENABLE_PIPELINE_TOOL=true

# CI providers (fill in the ones you use)
AZURE_DEVOPS_URL= / AZURE_DEVOPS_ORG= / AZURE_DEVOPS_PROJECT= / AZURE_DEVOPS_PAT=
JENKINS_URL= / JENKINS_USER= / JENKINS_TOKEN=
GITHUB_OWNER= / GITHUB_REPO= / GITHUB_TOKEN=
```

The full list, with comments, is in `.env.example`.

---

## Map of the repository

```text
ai_devops_assistant/
  main.py            # app factory, lifespan (DB init, LLM client shutdown)
  api/               # routes (/chat /run_sql /analyze_logs /metrics /health),
                     #   middleware, schemas, dependency injection
  agents/            # the agent loop, prompts, memory, prompt_manager (Jinja2)
  tools/             # BaseTool + the five tools + ToolRegistry/ToolExecutor
  services/          # llm_service (Ollama), anthropic_service (Claude),
                     #   multi_llm, model_registry
  rag/               # embeddings, Chroma vector store, ingestion, retriever, scraper
  database/          # async SQLAlchemy models, session, common queries
  observability/     # tracing + metrics for every LLM call and tool run
  config/            # settings.py — the single source of configuration
prompts/             # versioned prompt templates (Jinja2), loaded at runtime
infra/kubernetes/    # raw manifests + Helm chart (helm/) + secrets helpers
monitoring/          # Prometheus config + Grafana dashboards
tests/               # unit + integration (SQLite in-memory, mocked LLM)
.github/workflows/   # GitHub Actions CI/CD
azure-pipelines.yml  # Azure DevOps pipeline
Jenkinsfile          # Jenkins pipeline
docker-compose.yml   # the magic button
```

---

## When things go wrong

| Symptom | What's probably happening | Try this |
| --- | --- | --- |
| `/chat` times out the first time | The model is still loading into memory | Wait 30–60 s and try again |
| `/chat` errors, Ollama is up | Model not downloaded yet | `docker exec ai-devops-ollama ollama pull llama3` |
| Claude not answering | Key missing or provider not switched | Set `ANTHROPIC_API_KEY` + `LLM_PROVIDER`, restart |
| Database connection errors | Postgres down, or bad `DATABASE_URL` | `docker compose ps`, verify the URL |
| Connection refused on 8000 | Backend down or not port-forwarded | `docker ps`, or port-forward (see Kubernetes) |
| Pods stuck Pending | No storage class or low resources | `kubectl get storageclass`, `kubectl describe pod` |
| Tests fail on a fresh clone | Dev dependencies not installed | `pip install -e ".[dev]"` inside the venv |
| Pre-commit keeps complaining | It auto-fixed files; retry | `pre-commit run --all-files`, then `git add -u` |
| High memory usage | The LLM is hungry | Raise container limits, or use a smaller model |

More debugging:

```bash
docker compose logs -f backend            # watch the backend talk
kubectl set env deployment/ai-devops-assistant LOG_LEVEL=DEBUG -n ai-devops-assistant
```

---

## House rules (for humans and robots)

Simple rules that keep this project healthy — whether the contributor is a
person or an AI agent:

1. **Understand before changing.** Trace how the current flow works
   (route → agent → tool) before touching it.
2. **Small steps.** Prefer the smallest change that solves the problem; no
   surprise rewrites.
3. **Branch first.** `git switch -c feature/<short-name>` — don't commit to
   `master` directly.
4. **Tests always.** Run the suite before and after; add a regression test with
   every bug fix.
5. **Gate before pushing.** `pre-commit run --all-files` must be clean.
6. **Never commit secrets.** Use `.env` / `.env.local`; see
   [Secrets](#secrets-the-keys-to-your-house).
7. **Keep it observable.** New agent/tool functionality goes through the
   tracing layer; keep logs structured and never log secrets.
8. **Schema changes get migrations.** Backward-compatible first; no destructive
   data migrations without explicit approval.
9. **Docs follow code.** If behavior changes, this README changes too.
10. **When done, say what changed:** files touched, tests run, risks left.

For Claude Code specifically, `CLAUDE.md` in the repo root carries the
machine-focused version of this guidance.

---

## License

MIT — see the LICENSE file.
