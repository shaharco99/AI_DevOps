# AI DevOps Assistant

A production-grade, open-source platform demonstrating **AI Engineering + DevOps + Platform Architecture** for building intelligent DevOps automation systems.

This platform combines AI agent orchestration, retrieval-augmented generation (RAG), observability, and DevSecOps practices to create a comprehensive DevOps assistant that can diagnose issues, provide recommendations, and automate operational tasks.

## Project Overview

The AI DevOps Assistant is a full-stack platform that leverages large language models (LLMs) to provide intelligent DevOps capabilities. It features:

- **AI Agent System**: Tool-calling agents that can query databases, analyze logs, check metrics, and interact with CI/CD systems
- **RAG Pipeline**: Retrieval-augmented generation over DevOps documentation and runbooks
- **Multi-LLM Support**: Integration with Ollama, OpenAI, and Anthropic models
- **Observability Stack**: Prometheus + Grafana for monitoring AI usage and system health
- **DevSecOps Pipeline**: Comprehensive CI/CD with security scanning and quality gates
- **Kubernetes Deployment**: Production-ready Helm charts with high availability

## Architecture

```mermaid
flowchart TD
    U[DevOps Engineer / API Client] --> |HTTP| API[FastAPI Backend]
    API --> |Chat & Tool Requests| AGENT[LangChain Tool-Calling Agent]
    AGENT --> SQL[SQL Tool]
    AGENT --> K8S[Kubernetes Tool]
    AGENT --> LOGS[Log Analysis Tool]
    AGENT --> METRICS[Prometheus Metrics Tool]
    AGENT --> PIPE[Pipeline Status Tool]
    AGENT --> RAG[RAG Retrieval Tool]

    RAG --> CHROMA[(Chroma Vector Store)]
    RAG --> EMB[Ollama Embeddings]

    SQL --> POSTGRES[(PostgreSQL Database)]
    METRICS --> PROM[Prometheus Server]
    K8S --> CLUSTER[Kubernetes Cluster / API]
    PIPE --> AZDO[Azure DevOps REST API]
    API --> OLLAMA[Ollama LLM Service]
    PROM --> GRAFANA[Grafana Dashboards]

    EVAL[LLM Evaluator] --> API
    OBS[AI Observability] --> PROM
    BENCH[Model Benchmarking] --> API
```

### Core Components

- **AI Agent Framework**: LangChain-based tool-calling agents with memory and prompt management
- **RAG System**: Document ingestion, embedding generation, and semantic retrieval
- **Multi-LLM Service**: Unified interface for Ollama, OpenAI, and Anthropic models
- **Observability**: AI usage tracking, performance metrics, and error monitoring
- **Evaluation Framework**: Automated testing and quality assessment of LLM outputs
- **Benchmarking Suite**: Performance comparison across different models and configurations

## Features

### AI Capabilities
- **Conversational Interface**: Natural language queries about system status and issues
- **Tool Orchestration**: Automatic selection and execution of appropriate tools
- **Root Cause Analysis**: Intelligent diagnosis of deployment failures and incidents
- **Automated Remediation**: AI-generated suggestions for fixing common issues

### DevOps Integration
- **CI/CD Analysis**: Pipeline status checking and failure diagnosis
- **Infrastructure Monitoring**: Kubernetes cluster health and resource usage
- **Log Analysis**: Intelligent parsing and summarization of application logs
- **Metrics Correlation**: Relating system metrics to performance issues

### Data Processing
- **Web Scraping**: Automated ingestion of documentation and runbooks
- **Document Chunking**: Intelligent text segmentation for RAG
- **Vector Embeddings**: Semantic search over technical documentation
- **Knowledge Base**: Curated DevOps knowledge and best practices

### Production Features
- **High Availability**: Horizontal scaling and pod disruption budgets
- **Security Hardening**: Non-root containers and network policies
- **Secrets Management**: External secrets operator integration
- **Monitoring**: Comprehensive observability with Prometheus and Grafana

## Installation

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- kubectl (for Kubernetes deployment)
- Helm 3+ (for Helm deployment)

### Quick Start with Docker Compose

```bash
# Clone the repository
git clone https://github.com/yourusername/ai-devops-assistant.git
cd ai-devops-assistant

# Copy environment template
cp .env.example .env

# Start all services
docker-compose up -d

# Check service health
docker-compose ps

# View logs
docker-compose logs -f ai-devops-assistant
```

### Local Development Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Copy environment configuration
cp .env.example .env

# Run database migrations
alembic upgrade head

# Start the application
uvicorn ai_devops_assistant.main:app --reload
```

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and configure the following key variables:

```bash
# Application
API_ENVIRONMENT=development
LOG_LEVEL=INFO
SECRET_KEY=your-secret-key

# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost/devops

# LLM Configuration
LLM_PROVIDER=ollama
LLM_MODEL=llama3
OLLAMA_BASE_URL=http://localhost:11434

# External APIs
AZURE_DEVOPS_URL=https://dev.azure.com
AZURE_DEVOPS_ORG=your-org
AZURE_DEVOPS_PROJECT=your-project
AZURE_DEVOPS_PAT=your-pat

# Feature Flags
ENABLE_RAG=true
ENABLE_SCRAPING=true
ENABLE_EVALUATION=true
ENABLE_OBSERVABILITY=true
```

### Advanced Configuration

The application uses Pydantic settings for type-safe configuration. All settings are documented in `ai_devops_assistant/config/settings.py`.

## Running the System

### Starting Services

```bash
# With Docker Compose (recommended for development)
docker-compose up -d

# With Kubernetes
kubectl apply -f infra/kubernetes/namespace.yaml
kubectl apply -f infra/kubernetes/

# With Helm
helm install ai-devops-assistant infra/kubernetes/helm/
```

### API Access

Once running, access the API at `http://localhost:8000`

```bash
# Health check
curl http://localhost:8000/health

# API documentation
open http://localhost:8000/docs

# Chat interface
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Why did my pipeline fail?"}'
```

### Demo Script

Run the comprehensive demo to see all features:

```bash
# Run demo checks
./run_demo_checks.sh

# Or manually
python demo_checks.py
```

## Downloading LLM Models

The platform supports multiple LLM providers. Models are automatically downloaded on first use.

### Ollama Models (Local)

```bash
# Pull models via API
curl http://localhost:11434/api/pull -d '{"name": "llama3"}'

# Or via Kubernetes
OLLAMA_POD=$(kubectl get pod -n ai-devops-assistant -l app=ollama -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n ai-devops-assistant "$OLLAMA_POD" -- ollama pull llama3
```

### Model Registry

The application includes a model registry for discovering and downloading models:

```python
from ai_devops_assistant.services.model_registry import ModelRegistry

registry = ModelRegistry()
await registry.search_models("llama")
await registry.download_model("llama3:8b")
```

## Scraping Data

The platform can ingest documentation and runbooks for RAG:

### Web Scraping

```python
from ai_devops_assistant.rag.scraper import WebScraper

scraper = WebScraper()
documents = await scraper.scrape_url("https://kubernetes.io/docs/")
```

### Bulk Ingestion

```bash
# Scrape multiple sites
python -c "
from ai_devops_assistant.rag.scraper import SitemapScraper
scraper = SitemapScraper()
await scraper.scrape_sitemap('https://example.com/sitemap.xml')
"
```

### Document Processing

```python
from ai_devops_assistant.rag.document_ingestion import DocumentIngestion

ingestor = DocumentIngestion()
chunks = await ingestor.ingest_documents(documents)
```

## RAG Usage

The RAG system provides semantic search over technical documentation:

### Basic Retrieval

```python
from ai_devops_assistant.rag.retriever import RAGRetriever

retriever = RAGRetriever()
results = await retriever.retrieve("How to debug Kubernetes pods?")
```

### Pipeline Integration

```python
from ai_devops_assistant.rag.pipeline import RAGPipeline

pipeline = RAGPipeline()
response = await pipeline.query("Why is my deployment failing?")
```

### Vector Store Management

```python
from ai_devops_assistant.rag.vector_store import VectorStore

store = VectorStore()
await store.add_documents(chunks)
results = await store.search("deployment issues", limit=5)
```

## Deployment with kubectl

### Basic Deployment

```bash
# Create namespace
kubectl apply -f infra/kubernetes/namespace.yaml

# Deploy all components
kubectl apply -f infra/kubernetes/

# Check status
kubectl get pods -n ai-devops-assistant
kubectl get services -n ai-devops-assistant

# Port forward for access
kubectl port-forward svc/ai-devops-assistant 8000:80 -n ai-devops-assistant
```

### Troubleshooting kubectl Deployment

```bash
# Check pod status
kubectl get pods -n ai-devops-assistant

# View logs
kubectl logs -n ai-devops-assistant deployment/ai-devops-assistant

# Debug container issues
kubectl describe pod <pod-name> -n ai-devops-assistant

# Check events
kubectl get events -n ai-devops-assistant --sort-by='.lastTimestamp'
```

## Deployment with Helm

### Prerequisites

```bash
# Add Helm repositories
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add otwld https://otwld.github.io/ollama-helm/
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update
```

### Basic Installation

```bash
# Install with default values
helm install ai-devops-assistant infra/kubernetes/helm/ \
  --namespace ai-devops-assistant \
  --create-namespace

# Install with custom values
helm install ai-devops-assistant infra/kubernetes/helm/ \
  --namespace ai-devops-assistant \
  --values infra/kubernetes/helm/values-production.yaml
```

### Using the Deploy Script

```bash
# Deploy to production
./infra/kubernetes/helm/deploy.sh prod-release prod-namespace values-production.yaml

# Dry run
DRY_RUN=true ./infra/kubernetes/helm/deploy.sh
```

### Helm Features

- **Dependency Management**: Automatic PostgreSQL, Ollama, Prometheus, Grafana deployment
- **Security Hardening**: Non-root containers, network policies, secrets management
- **High Availability**: HPA, PDB, anti-affinity rules
- **External Secrets**: Vault/AWS Secrets Manager integration
- **Monitoring**: ServiceMonitors, custom dashboards

## Development Setup

### Code Quality Tools

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run linting
ruff check ai_devops_assistant/
black ai_devops_assistant/
isort ai_devops_assistant/

# Run tests
pytest tests/ -v --cov=ai_devops_assistant

# Type checking
mypy ai_devops_assistant/
```

### Pre-commit Hooks

```bash
# Install hooks
pre-commit install

# Run on all files
pre-commit run --all-files
```

### VS Code Configuration

The repository includes VS Code settings for:
- Python interpreter configuration
- Linting and formatting on save
- Debug configurations
- Task definitions

## Security Features

### DevSecOps Pipeline

- **SAST Scanning**: Bandit for Python security issues
- **Dependency Scanning**: pip-audit for vulnerable packages
- **Container Scanning**: Trivy for Docker image vulnerabilities
- **Secret Detection**: GitLeaks for credential leaks

### Runtime Security

- **Non-root Containers**: All containers run as non-root users
- **Network Policies**: Kubernetes network segmentation
- **Secrets Management**: External secrets operator integration
- **RBAC**: Proper service account permissions

### Code Security

```bash
# Run security scans
bandit -r ai_devops_assistant/
pip-audit
trivy image ghcr.io/yourusername/ai-devops-assistant:latest
```

## Troubleshooting

### Common Issues

#### Database Connection Issues

```bash
# Check database pod
kubectl logs -n ai-devops-assistant deployment/postgresql

# Test connection
kubectl exec -n ai-devops-assistant deployment/ai-devops-assistant -- python -c "
import asyncpg
import asyncio
async def test():
    conn = await asyncpg.connect('postgresql://user:pass@postgresql/db')
    await conn.close()
asyncio.run(test())
"
```

#### LLM Service Issues

```bash
# Check Ollama status
kubectl logs -n ai-devops-assistant deployment/ollama

# Test LLM connection
curl http://localhost:11434/api/tags
```

#### High Memory Usage

```bash
# Check resource usage
kubectl top pods -n ai-devops-assistant

# Adjust resource limits in values.yaml
resources:
  limits:
    memory: 2Gi
  requests:
    memory: 1Gi
```

### Debug Mode

```bash
# Enable debug logging
kubectl set env deployment/ai-devops-assistant LOG_LEVEL=DEBUG -n ai-devops-assistant

# View detailed logs
kubectl logs -n ai-devops-assistant deployment/ai-devops-assistant -f
```

### Performance Tuning

```yaml
# In values.yaml
autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 10

postgresql:
  primary:
    resources:
      limits:
        memory: 2Gi
      requests:
        memory: 1Gi
```

## API Examples

### Chat Interface

```bash
# Simple query
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Check the status of my Kubernetes pods"}'

# With context
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Why is the payment service slow?",
    "context": {"time_range": "1h"}
  }'
```

### Tool Execution

```bash
# Direct tool call
curl -X POST http://localhost:8000/tools/sql \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT * FROM deployments LIMIT 5"}'
```

### Health Checks

```bash
# Application health
curl http://localhost:8000/health

# Dependencies health
curl http://localhost:8000/health/dependencies
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

- **Documentation**: See `docs/` directory
- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions
- **Demo**: Run `./run_demo_checks.sh`
- `ai-devops-chroma`: The Chroma vector store service used for semantic search and retrieval-augmented generation (RAG).

In Kubernetes, these services map to pods/deployments as follows:

- `ai-devops-assistant`: The main backend deployment running the FastAPI service.
- `ollama`: The Ollama LLM deployment serving local model inference.
- `postgres`: The PostgreSQL deployment storing application data.
- `chroma`: The Chroma vector database deployment for embeddings and document search.
- `prometheus`: The Prometheus deployment scraping metrics from the application and cluster.
- `grafana`: The Grafana deployment providing dashboards and data visualization.

### What Each Pod / Container Does

- `ai-devops-backend` / `ai-devops-assistant`
  - Exposes the `/chat`, `/run_sql`, `/analyze_logs`, `/metrics`, and `/health` endpoints.
  - Manages request validation, tool orchestration, configuration, and logging.
  - Calls the agent layer to decide whether to use SQL, K8s, logs, metrics, or RAG to answer the user.

- `ai-devops-ollama` / `ollama`
  - Hosts the local Ollama inference engine.
  - Responds to prompt completions and tool-calling decisions.
  - Stores downloaded models in persistent storage so the assistant can use them offline.

- `ai-devops-postgres` / `postgres`
  - Stores structured state for the assistant, including pipeline records, logs, and operational metadata.
  - Serves as the primary relational database for SQL tool queries.

- `ai-devops-chroma` / `chroma`
  - Stores semantic embeddings and document vectors.
  - Powers retrieval of runbooks, documentation, and contextual knowledge for RAG-enhanced answers.

- `ai-devops-prometheus` / `prometheus`
  - Scrapes metrics from the backend service and supported endpoints.
  - Stores time-series metrics for dashboards and analysis.
  - Enables queries such as HTTP latency, error rate, and resource health.

- `ai-devops-grafana` / `grafana`
  - Visualizes metrics from Prometheus.
  - Provides preconfigured dashboards for service health, request performance, and cluster monitoring.

- `ai-devops-redis`
  - Optional cache layer used for temporary tool results and accelerated runtime performance.
  - Helps reduce repeated work for repeated queries.

## Tech Stack

- **Backend**: Python, FastAPI, SQLAlchemy
- **AI**: LangChain, tool-calling agents, RAG, Chroma
- **LLM**: Ollama (`llama3`, `mistral`, `nomic-embed-text`)
- **Data**: PostgreSQL
- **Observability**: Prometheus, Grafana
- **Platform**: Docker, Docker Compose, Kubernetes manifests
- **CI/CD & Security**: GitHub Actions, Ruff, Black, MyPy, Pytest, Bandit, pip-audit, Trivy

## Repository Layout

```text
ai_devops_assistant/
  agents/ tools/ rag/ database/ services/ api/
infra/
  kubernetes/
    helm/           # Helm chart for Kubernetes deployment
    *.yaml          # Individual Kubernetes manifests
monitoring/
  prometheus/ grafana/
tests/
.github/workflows/     # GitHub Actions CI/CD
azure-pipelines.yml    # Azure DevOps pipeline
Jenkinsfile           # Jenkins pipeline
```

## Quick Start (Docker)

```bash
git clone https://github.com/yourusername/ai-devops-assistant.git
cd ai-devops-assistant

# For local development: copy and customize environment variables
cp .env.example .env.local

# Edit .env.local with your credentials (see .env.local.example for details)
# DO NOT commit .env.local - it's automatically in .gitignore

docker compose up -d
docker exec ai-devops-ollama ollama pull llama3
docker exec ai-devops-ollama ollama pull nomic-embed-text
curl -s http://localhost:8000/health
```

**⚠️ Secrets Management**: Never commit `.env` files with real credentials. See [SECRETS_MANAGEMENT.md](./SECRETS_MANAGEMENT.md) for best practices on handling API keys, tokens, and PATs securely in development and production.

Endpoints:

- API docs: `http://localhost:8000/docs`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000` (admin/admin)

## Interview Demo Script (High-Signal)

### Demo Path A: Docker-based (10-15 min)

```bash
# 1) Start platform
docker compose up -d
docker compose ps

# 2) Verify health and observability
curl -s http://localhost:8000/health
curl -s "http://localhost:9090/api/v1/query?query=up"

# 3) Ask operational AI questions
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Why did my pipeline fail?"}'

curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Which service has the highest latency?"}'

# 4) Show SQL safety controls
curl -X POST http://localhost:8000/run_sql \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT * FROM application_logs LIMIT 5"}'

# 5) Show blocked unsafe query
curl -X POST http://localhost:8000/run_sql \
  -H "Content-Type: application/json" \
  -d '{"query":"DROP TABLE application_logs"}'
```

### Demo Path B: Kubernetes + Minikube (Platform Skills)

```bash
# 1) Start local cluster
minikube start --cpus=4 --memory=8192

# 2) Apply namespace first, then deploy stack manifests
kubectl apply -f infra/kubernetes/namespace.yaml
kubectl apply -f infra/kubernetes/
kubectl get pods -n ai-devops-assistant

# 3) Ensure model exists in in-cluster Ollama
OLLAMA_POD=$(kubectl get pod -n ai-devops-assistant -l app=ollama -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n ai-devops-assistant "$OLLAMA_POD" -- ollama pull llama3

# 4) Validate rollout + runtime health
kubectl rollout status deploy/ai-devops-assistant -n ai-devops-assistant

# Temporary port-forward for API checks
kubectl port-forward svc/ai-devops-assistant 8000:80 -n ai-devops-assistant
curl -s http://localhost:8000/health

# 5) Trigger AI troubleshooting
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Show failing pods and explain likely root cause"}'
```

## Security Skills Showcase

- SQL guardrails: only safe read-style SQL accepted by tool layer.
- Secret hygiene: env-based configuration; no plaintext credentials in code.
- CI checks:
  - `bandit` for static security analysis.
  - `pip-audit` for dependency CVEs.
  - `trivy` for filesystem/container vulnerability scanning.
- Supply chain posture: deterministic Docker builds, non-root runtime container.

## CI/CD Pipeline Stages

GitHub Actions pipeline includes:

- **lint**: Ruff + Black + MyPy
- **unit-tests**: pytest + coverage
- **docker-build**: image build validation
- **security-scan**: Bandit + pip-audit + Trivy (SARIF upload)

## Deployment Options

### GitHub Actions (Already Configured)

The repository includes GitHub Actions workflows in `.github/workflows/`:

- `ci-cd.yml`: Main CI pipeline with linting, testing, Docker build, and security scanning
- `release.yml`: Automated Docker image building and publishing to GitHub Container Registry
- `security.yml`: Scheduled security scans with Trivy and CodeQL
- `dependency-review.yml`: Dependency vulnerability checking

**To use GitHub Actions:**

1. Push your code to a GitHub repository
2. Ensure GitHub Container Registry is enabled
3. The workflows will run automatically on push/PR to main/develop branches

### Azure DevOps Pipelines

Create a new pipeline using the provided `azure-pipelines.yml`:

1. In Azure DevOps, go to Pipelines → New Pipeline
2. Select "GitHub" as source and connect your repository
3. Choose "Existing Azure Pipelines YAML file"
4. Select `azure-pipelines.yml` from the root
5. Configure these variables in Pipeline Variables:
   - `DOCKER_REGISTRY`: Your Azure Container Registry URL
   - Set up service connections for Azure Container Registry and Kubernetes

### Jenkins Pipeline

Use the provided `Jenkinsfile` for Jenkins:

1. Install required Jenkins plugins:
   - Docker Pipeline
   - Kubernetes CLI
   - Cobertura (for coverage reports)
   - JUnit (for test reports)

2. Configure Jenkins credentials:
   - `docker-registry-credentials`: For pushing to your container registry
   - `kubeconfig`: For Kubernetes deployment

3. Create a new Pipeline job and copy the `Jenkinsfile` content

4. Configure the environment variables in the Jenkins job:
   - `DOCKER_REGISTRY`: Your container registry URL

### Deployment to Kubernetes

After CI/CD completes successfully:

```bash
# Using kubectl directly
kubectl apply -f infra/kubernetes/namespace.yaml
kubectl apply -f infra/kubernetes/

# Or using Helm (if available)
kubectl apply -f infra/kubernetes/namespace.yaml && helm upgrade ai-devops-assistant infra/kubernetes/helm/

# Check deployment status
kubectl get pods -n ai-devops-assistant
kubectl rollout status deployment/ai-devops-assistant -n ai-devops-assistant
```

### How the AI Assistant Connects to Azure DevOps

When you ask "Why did my pipeline fail?", here's what happens:

1. **User Query** → AI Agent receives: *"Why did my pipeline fail?"*

2. **Tool Selection** → Agent uses LLM to decide which tool to call:
   - Recognizes this as a pipeline-related question
   - Calls the `pipeline_status_tool` with action `get_recent_builds`

3. **Azure DevOps API Call** → Pipeline tool makes authenticated API calls:

   ```python
   # Tool executes this logic:
   async def _get_recent_builds(self, pipeline_name=None):
       url = f"{AZURE_DEVOPS_URL}/{ORG}/{PROJECT}/_apis/build/builds"
       headers = {"Authorization": f"Basic {base64_PAT}"}
       # Fetches recent builds via REST API
   ```

4. **Data Retrieval** → Gets real pipeline data:
   - Build status, results, timestamps
   - Failed task details and logs
   - Source branch and commit info

5. **Analysis & Response** → Agent synthesizes findings:
   - Identifies failed builds
   - Explains likely root causes
   - Suggests remediation steps

#### Required Environment Variables

```bash
# Set these in your deployment environment
AZURE_DEVOPS_URL=https://dev.azure.com          # Your Azure DevOps URL
AZURE_DEVOPS_ORG=your-organization               # Organization name
AZURE_DEVOPS_PROJECT=your-project                # Project name
AZURE_DEVOPS_PAT=your-personal-access-token      # PAT with Build (Read) permissions
```

#### Example Conversation Flow

**User:** "Why did my pipeline fail?"
**Agent:** (calls pipeline tool) → (queries Azure DevOps API) → (gets failed build data)
**Agent:** "The latest pipeline run #2024.04.23.1 failed during the 'Unit Tests' stage. The error shows a test failure in `test_api.py` line 45. The logs indicate a database connection timeout. This commonly occurs when the test database isn't ready. Try increasing the retry count or adding a health check before running tests."

#### Azure DevOps Configuration

**For Docker Deployment:**

```bash
# Add to your .env file
AZURE_DEVOPS_URL=https://dev.azure.com
AZURE_DEVOPS_ORG=your-org-name
AZURE_DEVOPS_PROJECT=your-project-name
AZURE_DEVOPS_PAT=your-personal-access-token
```

**For Kubernetes Deployment:**

```yaml
# Add to infra/kubernetes/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: ai-devops-config
  namespace: ai-devops-assistant
data:
  AZURE_DEVOPS_URL: "https://dev.azure.com"
  AZURE_DEVOPS_ORG: "your-org-name"
  AZURE_DEVOPS_PROJECT: "your-project-name"

---
apiVersion: v1
kind: Secret
metadata:
  name: ai-devops-secrets
  namespace: ai-devops-assistant
type: Opaque
data:
  AZURE_DEVOPS_PAT: <base64-encoded-pat>
```

**Creating Azure DevOps PAT:**

1. Go to Azure DevOps → User Settings → Personal Access Tokens
2. Create new token with "Build (Read)" and "Project (Read)" scopes
3. Copy the token value to your environment variables

The assistant becomes your **intelligent DevOps companion** that can instantly diagnose pipeline issues by connecting directly to your Azure DevOps environment!

## API Examples

```bash
curl -X POST http://localhost:8000/analyze_logs \
  -H "Content-Type: application/json" \
  -d '{"query":"ERROR","time_range_hours":24,"limit":50}'

curl -X POST http://localhost:8000/metrics \
  -H "Content-Type: application/json" \
  -d '{"query":"histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))"}'
```

## Running Demo Checks

Validate your deployment with automated checks:

```bash
# Method 1: Using Python directly
python3 demo_checks.py

# Method 2: Using shell wrapper (handles venv activation)
bash run_demo_checks.sh
```

### Expected Results

#### Demo Path A: Docker Deployment

When running demo checks after `docker compose up -d`:

```
✓ Docker daemon is running
✓ Found 8 AI DevOps container(s) running
  - ai-devops-api
  - ai-devops-ollama
  - ai-devops-postgres
  - ai-devops-chroma
  - ai-devops-prometheus
  - ai-devops-grafana
  ...

✓ General health: 200
✓ Liveness probe: 200
✓ Readiness probe: 200
  Status: ready

✓ /chat endpoint: OK (200)
  Response: Based on current metrics...

✓ /analyze_logs endpoint: OK (200)
✓ /metrics endpoint: OK (200)
✓ Prometheus: OK
✓ Grafana: OK
✓ All unit tests passed
```

**What it means:**

- All containers are running and healthy
- API is responding to requests
- Chat/LLM functionality is working (Ollama model available)
- Prometheus is collecting metrics
- Grafana is accessible for visualization
- Core functionality tests pass

#### Demo Path B: Kubernetes Deployment

When running demo checks after `kubectl apply -f infra/kubernetes/`:

```
✓ Connected to Kubernetes cluster
  Version: v1.28.0

✓ Namespace 'ai-devops-assistant' exists

✓ Found 6 pod(s) in namespace
  - ai-devops-assistant-<hash>: Running
  - ollama-<hash>: Running
  - postgres-<hash>: Running
  - chroma-<hash>: Running
  - prometheus-<hash>: Running
  - grafana-<hash>: Running

✓ Found 4 deployment(s)

✓ General health: 200
✓ Liveness probe: 200
✓ Readiness probe: 200
```

**What it means:**

- Kubernetes cluster is accessible
- All required resources are deployed in the namespace
- Pods are in Running state
- API is responding through Kubernetes service

### Demo Check Components

| Check | Purpose | Success Indicator |
|-------|---------|-------------------|
| **Deployment Detection** | Identify Docker or Kubernetes | One method detected with running services |
| **Container/Pod Status** | Verify all components running | All containers/pods in Running state |
| **Health Endpoints** | API responsiveness | 200 status code on all /health/* paths |
| **Chat Endpoint** | LLM integration | 200 response with content |
| **Log Analysis** | Database connectivity | 200 or 400 (expected if no logs) |
| **Metrics Endpoint** | Prometheus integration | 200 response with data |
| **Observability Stack** | Monitoring availability | Prometheus and Grafana accessible |
| **Unit Tests** | Core functionality | All tests pass |

### Troubleshooting Demo Checks

**"No AI DevOps deployment detected"**

- For Docker: Run `docker compose up -d` in the repo root
- For Kubernetes: Run `kubectl apply -f infra/kubernetes/`

**"API Health Checks: Connection refused"**

- For Docker: Ensure containers are running (`docker ps`)
- For Kubernetes: Port-forward with `kubectl port-forward svc/ai-devops-assistant 8000:80`

**"/chat endpoint: Timeout"**

- Normal during first LLM inference (model loading)
- Ollama is running but model initialization takes 30+ seconds
- Try again after waiting for model to load

**"Unit tests failed"**

- Ensure virtual environment is activated: `source venv/bin/activate`
- Install dev dependencies: `pip install -r requirements.txt`

## Local Development

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"
pre-commit install
pytest tests/unit -v
```

### Testing Azure DevOps Integration

```bash
# Set your Azure DevOps environment variables
export AZURE_DEVOPS_URL="https://dev.azure.com"
export AZURE_DEVOPS_ORG="your-organization"
export AZURE_DEVOPS_PROJECT="your-project"
export AZURE_DEVOPS_PAT="your-personal-access-token"

# Run the test script
python test_azure_devops.py
```

This will verify that the pipeline tool can successfully connect to your Azure DevOps environment and retrieve pipeline information.

## Documentation

- `ARCHITECTURE.md`
- `IMPLEMENTATION_PLAN.md`
- `infra/kubernetes/README.md`

---

# Code Quality & Development Improvements

This section documents the comprehensive quality, security, and development workflow enhancements added to the project.

## 1. Code Linting & Static Analysis

### Tools Used

**Ruff** - Modern, fast Python linter

- **What it does**: Scans Python code for style violations, logical errors, and potential bugs
- **Why it improves the project**:
  - Fast linting (10x faster than Flake8)
  - Catches bugs early in development
  - Maintains consistent code style across the team
  - Integrates seamlessly into CI/CD pipelines

### Configuration

- **Config file**: `pyproject.toml` under `[tool.ruff]`
- **Enabled checks**: E (errors), F (PyFlakes), W (warnings), I (isort), N (naming), UP (upgrades)
- **CI Integration**: Runs on every PR/commit via GitHub Actions

### Usage

```bash
# Check for violations
ruff check ai_devops_assistant/

# Fix automatically
ruff check --fix ai_devops_assistant/
```

---

## 2. PEP8 Code Style Enforcement

### Tools Used

**Black** - Uncompromising code formatter
**isort** - Import statement organizer

- **What they do**:
  - Black: Automatically formats Python code to PEP 8 standard with a consistent, opinionated style
  - isort: Sorts and organizes imports in a standard order

- **Why they improve the project**:
  - Eliminates style discussions in code reviews
  - Auto-formats on save in VS Code
  - Runs as pre-commit hook
  - Ensures consistency across multiple developers

### Configuration

- **Black config**: `pyproject.toml` - line length 100
- **isort config**: `pyproject.toml` - Black-compatible profile
- **Integration**: Runs on every commit via pre-commit

### Usage

```bash
# Format code
black ai_devops_assistant/

# Sort imports
isort ai_devops_assistant/

# Or run both via pre-commit
pre-commit run --all-files
```

### Difference: Formatter vs Linter

- **Linter** (Ruff): Identifies problems and style issues but doesn't fix them
- **Formatter** (Black): Automatically fixes style issues and enforces a consistent format
- **Together**: Ruff finds issues, Black fixes them, creating a zero-friction workflow

---

## 3. Environment Variables Management

### Tools Used

**python-dotenv** - Loads environment variables from .env files
**pydantic-settings** - Type-safe configuration management

- **What it does**:
  - Centralized configuration through .env files
  - Type validation for all settings
  - Support for different environments (dev, staging, prod)
  - Secure handling of sensitive data

### Configuration Files

- `.env.example` - Template with all available configuration options
- `.env` (git-ignored) - Local development environment
- `ai_devops_assistant/config/settings.py` - Pydantic settings model

### Why Environment Separation Improves Security

1. **Secrets Not in Code**: Database passwords, API keys never committed to git
2. **Environment-Specific**: Different configs for dev, test, production
3. **Easy Rotation**: Change secrets without code changes
4. **Type Safety**: Pydantic validates all settings on startup
5. **Clear Documentation**: `.env.example` shows all available options

### Supported Configurations

```env
# Multi-LLM Support
LLM_PROVIDER="ollama"           # ollama | openai | anthropic | huggingface
OPENAI_API_KEY="sk-..."
ANTHROPIC_API_KEY="..."
HUGGINGFACE_API_KEY="..."

# Feature Flags
ENABLE_RAG=true
ENABLE_SCRAPING_TOOL=true
ENABLE_FINETUNING=false

# Fine-tuning
FINETUNING_LEARNING_RATE=2e-5
FINETUNING_NUM_EPOCHS=3
```

### Usage

```bash
# Copy template and configure
cp .env.example .env
vim .env

# Settings are automatically loaded on app startup
# Access via: from ai_devops_assistant.config.settings import settings
```

---

## 4. Structured Logging System

### Current Implementation

**python-json-logger** - JSON structured logging

- **What it does**:
  - Outputs logs in structured JSON format
  - Includes timestamps, log levels, logger names
  - Supports custom fields and context

- **Why it improves the project**:
  - Logs are machine-parseable
  - Easy to aggregate in log management systems (ELK, Datadog, CloudWatch)
  - Includes all context needed for debugging
  - Production-ready observability

### Features

- **JSON Format**: Machine-readable logs for log aggregation
- **Text Format**: Human-readable format for local development
- **Configurable**: Switch via `LOG_FORMAT` environment variable
- **Log Levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL

### Usage

```python
import logging
from ai_devops_assistant.config.logging import get_logger

logger = get_logger(__name__)
logger.info("Processing request", extra={"request_id": "123"})
logger.error("Failed to process", exc_info=True)
```

### Enhanced Logging Features

**Request Tracing**: Unique request IDs for end-to-end tracing
**Error Stack Traces**: Full context for production debugging
**Performance Metrics**: Log operation durations

```python
# Example with request context
logger.info("Processing DevOps query", extra={
    "request_id": request_id,
    "tool": "kubernetes",
    "duration_ms": 125,
    "status": "success"
})
```

---

## 5. LLM Registry Integration

### Tool Used

**Hugging Face Hub + Ollama Registry**

- **What it does**:
  - Discover and download LLM models from registries
  - Support for model metadata and filtering
  - Automatic local model management

- **Why it improves the project**:
  - Easy model discovery without manual URLs
  - Support for multiple model sources
  - Automated model downloading
  - Version management

### Features

- **Hugging Face Registry**: Access to thousands of open-source models
- **Ollama Registry**: Local model management
- **Composite Registry**: Search across multiple sources
- **Metadata**: Model size, parameters, ratings, downloads

### Usage

```python
from ai_devops_assistant.services.model_registry import CompositeRegistry

registry = CompositeRegistry()

# Search for models
models = await registry.search_models("llama", limit=10)

# Get model information
model_info = await registry.get_model_info("meta-llama/Llama-2-7b")

# Download via Ollama
ollama = OllamaRegistry()
ollama.download_model("llama3")
```

---

## 6. Multi-LLM Support

### Abstraction Layer Implementation

Support for multiple LLM providers with unified interface:

- **Ollama** (local, free)
- **OpenAI** (cloud-based)
- **Anthropic Claude** (cloud-based)
- **HuggingFace Transformers** (local/cloud)

- **What it does**:
  - Single interface for all LLM providers
  - Easy switching between providers via configuration
  - Fallback model support for resilience
  - Streaming and non-streaming modes

- **Why it improves the project**:
  - Not locked into one provider
  - Easy to switch providers for cost/performance
  - Test different models without code changes
  - Supports both open-source and commercial models

### Usage

```python
from ai_devops_assistant.services.multi_llm import LLMFactory

# Create provider (configured via LLM_PROVIDER env var)
llm = LLMFactory.create("openai", api_key="sk-...")

# Generate text
response = await llm.generate("Analyze this log", max_tokens=2048)

# Stream generation
async for chunk in await llm.stream_generate(prompt):
    print(chunk, end="", flush=True)
```

### Configuration

```python
# Switch providers via environment
LLM_PROVIDER="openai"          # Primary provider
OPENAI_API_KEY="sk-..."

# Or fallback to local Ollama
LLM_PROVIDER="ollama"
OLLAMA_BASE_URL="http://localhost:11434"
LLM_MODEL="llama3"
```

---

## 7. Secure Requirements.txt

### Best Practices Implemented

- **Version Pinning**: Exact versions for reproducibility
- **Python Version Markers**: Compatibility specifications
- **Platform Markers**: OS-specific requirements
- **No Vulnerable Packages**: Regular pip-audit scanning

### Example

```
requests==2.31.0           # Pinned version
python-json-logger==2.0.7  # Tested and compatible
```

### Dependency Supply Chain Security

1. **Pinned Versions**: Prevents supply chain attacks via version hijacking
2. **Regular Updates**: Weekly dependency checks via CI
3. **Vulnerability Scanning**: pip-audit identifies CVEs
4. **Transitive Dependencies**: All dependencies tracked and secured
5. **License Compliance**: Compatible with MIT project license

### CI Scanning

- `pip-audit` runs on every commit to detect vulnerabilities
- GitHub Security tab shows advisories
- Automatic alerts for new CVEs

---

## 8. SAST Security Scanning

### Tools Used

**Bandit** - Python security issue scanner

- **What it does**:
  - Scans Python code for security vulnerabilities
  - Detects hardcoded credentials, SQL injection risks, insecure crypto
  - Provides severity ratings and remediation guidance

- **Why it improves the project**:
  - Catches security bugs before production
  - Prevents credential leaks in code
  - Enforces secure coding practices
  - CI/CD integration for automatic enforcement

### Configuration

- **Config**: `pyproject.toml` under `[tool.bandit]`
- **Skips**: Unit tests (not production code)
- **Levels**: High, medium, low severity

### Usage

```bash
# Scan for security issues
bandit -r ai_devops_assistant/

# Run specific test
bandit -r ai_devops_assistant/ -t B101  # Test for assertions
```

### Security Findings

Common issues detected:

- Hardcoded passwords/tokens
- Insecure random generation
- Use of pickle with untrusted input
- SQL injection vulnerabilities
- Insecure cipher usage

---

## 9. Website Scraping Ingestion Pipeline

### Implementation

**BeautifulSoup** - HTML parsing and web scraping

- **What it does**:
  - Scrapes website content for ingestion into RAG system
  - Extracts text, links, and metadata
  - Supports sitemap-based crawling
  - Respects robots.txt rules

- **Why it improves the project**:
  - Ingest documentation and runbooks from websites
  - Keep RAG knowledge updated automatically
  - Support for team wikis and knowledge bases
  - Respect crawling etiquette via robots.txt

### Scraper Architecture

```
WebScraper
├── Basic URL scraping
├── Text extraction (remove nav, footer, scripts)
├── Link extraction (same-domain only)
└── Metadata extraction (title, description, keywords)

SitemapScraper
├── Parse sitemap.xml
├── Concurrent scraping (configurable workers)
└── Automatic batch processing

RobotsTxtParser
├── Check /robots.txt rules
├── Respect Disallow directives
└── Rate limiting support
```

### Usage

```python
from ai_devops_assistant.rag.scraper import WebScraper, SitemapScraper

scraper = WebScraper()

# Scrape single URL
content = await scraper.scrape_url("https://runbook.example.com/incident")

# Scrape multiple URLs concurrently
urls = ["https://...", "https://..."]
contents = await scraper.scrape_urls(urls)

# Scrape entire site via sitemap
sitemap_scraper = SitemapScraper(scraper)
contents = await sitemap_scraper.scrape_from_sitemap(
    "https://example.com/sitemap.xml",
    max_pages=1000
)

# Ingest into RAG
for content in contents:
    await rag_system.add_document(
        content=content.content,
        metadata={"url": content.url, "title": content.title}
    )
```

### Configuration

```
SCRAPING_USER_AGENT="AI-DevOps-Assistant/1.0"
SCRAPING_TIMEOUT=30                      # seconds
SCRAPING_MAX_WORKERS=5                   # concurrent requests
SCRAPING_ENABLE_JAVASCRIPT=false         # Playwright not enabled by default
```

---

## 10. Markdown Linting

### Tool Used

**markdownlint** - Markdown style and consistency checker

- **What it does**:
  - Validates Markdown syntax and style
  - Enforces consistent formatting
  - Checks for common Markdown mistakes

- **Why it improves the project**:
  - Professional documentation
  - Consistent across team
  - Rendering issues caught early
  - CI/CD enforcement

### Configuration

`.markdownlint.json` - Defines rules and exceptions:

```json
{
  "line-length": {"line_length": 120},
  "proper-names": {"names": ["AI DevOps Assistant", "Kubernetes", ...]},
  "heading-increment": true,
  "list-item-content-indent": false
}
```

### Usage

```bash
# Lint all markdown
markdownlint-cli2 "**/*.md"

# Auto-fix
markdownlint-cli2 "**/*.md" --fix
```

---

## 11. Typo Detection

### Tool Used

**codespell** - Spell checker for source code

- **What it does**:
  - Detects spelling errors in code and documentation
  - Checks comments, docstrings, variable names
  - Customizable ignore list for false positives

- **Why it improves the project**:
  - Professional documentation quality
  - Prevents embarrassing typos in code
  - Improves readability
  - Team consistency

### Configuration

`.codespellrc` - Rules and ignore patterns:

```
skip = .git,.*,*.pyc,.env.example,*.lock
ignore-words-list = cna,nd,sav,ser,ans  # Common false positives
```

### Usage

```bash
# Check for spelling errors
codespell ai_devops_assistant/

# Fix automatically
codespell -i ai_devops_assistant/ --fix
```

---

## 12. SCA (Dependency Vulnerability Scanning)

### Tool Used

**pip-audit** - Software Composition Analysis for Python

- **What it does**:
  - Scans dependencies for known vulnerabilities
  - Checks against vulnerability databases
  - Provides remediation guidance

- **Why it improves the project**:
  - **Supply Chain Security**: Protects against known vulnerabilities in dependencies
  - **CVE Detection**: Automatically finds publicly disclosed vulnerabilities
  - **Update Guidance**: Recommends patched versions
  - **Compliance**: Meets security audit requirements

### Usage

```bash
# Scan installed packages
pip-audit

# Scan requirements file
pip-audit -r requirements.txt

# Check specific package
pip-audit --desc requests
```

### CI Integration

Runs automatically on every commit:

```yaml
- name: Run pip-audit vulnerability scan
  run: pip-audit -r requirements.txt
```

---

## 13. Local LLM Fine-Tuning Workflow

### Implementation

**HuggingFace PEFT** - Parameter-Efficient Fine-Tuning with LoRA/QLoRA

- **What it does**:
  - Fine-tune local LLMs on custom data
  - LoRA: Efficient fine-tuning by adapting weights
  - QLoRA: Quantized LoRA for smaller models
  - Works with existing Ollama models

- **Why it improves the project**:
  - Adapt models to DevOps-specific language
  - Reduce inference costs (smaller models)
  - Maintain privacy (local training)
  - Improve domain-specific performance

### How Fine-Tuning Works

```
Base Model (e.g., Llama 3)
    ↓
Apply LoRA Adapters (adds ~1% parameters)
    ↓
Fine-tune only adapters on custom data
    ↓
Merge adapters with base model
    ↓
Deploy fine-tuned model
```

### Usage

```python
from ai_devops_assistant.ml.finetuning import FineTuner, FineTuningConfig

config = FineTuningConfig(
    model_name="meta-llama/Llama-2-7b",
    learning_rate=2e-5,
    num_epochs=3,
    batch_size=8,
    use_qlora=True  # For smaller GPUs
)

finetuner = FineTuner(config)

# Load model
finetuner.load_model()

# Prepare training data
finetuner.prepare_dataset("./training_data.jsonl")

# Train
finetuner.train()

# Model saved to ./finetuned_models/
```

### Training Data Format

```jsonl
{"text": "Incident: High CPU on Kubernetes node. Root cause: Memory leak in deployment. Solution: Restart pod"}
{"text": "Alert: Database connection timeout. Troubleshooting: Check network, verify credentials, monitor connections"}
```

---

## 14. Prompt Management System

### Implementation

**Jinja2 Templates** - Versioned prompt management

- **What it does**:
  - Central repository for all system prompts
  - Version control for prompts
  - Template variables for dynamic prompts
  - Category organization

- **Why it improves the project**:
  - **Versioning**: Track prompt changes and rollbacks
  - **Collaboration**: Team can manage prompts independently
  - **Reusability**: Share prompts across agents
  - **Testing**: A/B test different prompts
  - **Documentation**: Each prompt has clear intent

### Directory Structure

```
prompts/
├── README.md
├── system/
│   └── devops_assistant.md         # Main system prompt
├── rag/
│   └── synthesis.md                # RAG synthesis prompts
├── agents/
│   └── incident_analysis.md        # Agent-specific prompts
└── tools/
    └── kubernetes.md               # Tool-specific prompts
```

### Usage

```python
from ai_devops_assistant.agents.prompt_manager import PromptManager

manager = PromptManager()

# Load and render prompt
prompt_template = manager.load_prompt("devops_assistant", version="1.0")
rendered = manager.render_prompt(prompt_template, context={
    "issue_type": "high_cpu",
    "severity": "critical"
})

# List available prompts
prompts = manager.list_prompts(category="system")

# Get metadata
metadata = manager.get_prompt_metadata("devops_assistant")
print(f"Version: {metadata.version}, Status: {metadata.status}")
```

### Prompt Template Example

```markdown
# DevOps Assistant System Prompt

**Purpose**: Main system prompt
**Version**: 1.0
**Status**: Active

---

You are an expert AI DevOps Assistant...

### Context
- Issue Type: {{ issue_type }}
- Severity: {{ severity }}

### Responsibilities
[...]
```

### Benefits

1. **Experimentation**: A/B test different prompts
2. **Version Control**: Track changes, rollback easily
3. **Team Collaboration**: Share and improve prompts together
4. **Documentation**: Self-documenting prompts
5. **Consistency**: Reuse proven prompts

---

## 15. VS Code Team Development Setup

### Configuration Files

#### `.vscode/settings.json`

Consistent development environment for all team members:

```json
{
  "[python]": {
    "editor.defaultFormatter": "ms-python.python",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.organizeImports": "explicit"
    }
  },
  "editor.rulers": [100, 120],
  "files.trimTrailingWhitespace": true,
  "files.insertFinalNewline": true
}
```

#### `.vscode/extensions.json`

Recommended extensions for the project:

```json
{
  "recommendations": [
    "ms-python.python",
    "charliermarsh.ruff",
    "ms-python.black-formatter",
    "eamodio.gitlens",
    "ms-kubernetes-tools.vscode-kubernetes-tools"
  ]
}
```

#### `.vscode/launch.json`

Pre-configured debugging for common tasks:

```json
{
  "configurations": [
    {
      "name": "Python: FastAPI Backend",
      "module": "uvicorn",
      "args": ["ai_devops_assistant.main:app", "--reload"]
    },
    {
      "name": "Python: Debug Tests",
      "module": "pytest",
      "args": ["${file}", "-v", "-s"]
    }
  ]
}
```

### How This Improves Team Consistency

1. **Unified Settings**: All team members see same rulers, line lengths
2. **Automatic Formatting**: No debates about style
3. **Recommended Extensions**: Everyone has required tools
4. **Debugging Configs**: Standardized debugging experience
5. **Git Integration**: Built-in Git Graph and Gitlens

### Setup for New Team Members

```bash
# Clone repo
git clone ...

# VS Code automatically recommends extensions on first open
# Accept recommendations to install

# Editor settings automatically applied
# No setup needed!
```

---

## 16. Pre-commit Hooks

### Tools Integrated

- **Ruff & Ruff Format**: Linting and formatting
- **Black**: Code formatting
- **isort**: Import sorting
- **MyPy**: Type checking
- **Bandit**: Security scanning
- **Markdownlint**: Documentation linting
- **Codespell**: Spell checking
- **pip-audit**: Dependency scanning

### Configuration

`.pre-commit-config.yaml` - Comprehensive hook setup:

- Runs before each commit
- Auto-fixes issues when possible
- Prevents pushing bad code

### Setup & Usage

```bash
# One-time setup
pre-commit install

# Automatically runs on commit
git commit -m "Add new feature"

# Manual run
pre-commit run --all-files

# Update hooks
pre-commit autoupdate
```

### Benefits

1. **Catch Issues Early**: Before code review
2. **Auto-fix**: Many issues fixed automatically
3. **Team Consistency**: Everyone uses same checks
4. **Fail Fast**: Prevents bad commits
5. **CI Integration**: Redundant to CI but faster locally

---

## 17. CI/CD Pipeline

### GitHub Actions Workflows

Comprehensive CI/CD covering all aspects:

#### Jobs Run on Every Commit

1. **Lint** (Multi-version):
   - Ruff linting
   - Black formatting check
   - isort import check
   - MyPy type checking
   - Pylint analysis

2. **Unit Tests** (Python 3.11, 3.12):
   - With PostgreSQL service
   - Coverage reporting
   - Codecov upload

3. **Integration Tests**:
   - End-to-end testing
   - Database operations
   - External API calls (mocked)

4. **Security Scans**:
   - **SAST**: Bandit security analysis
   - **SCA**: pip-audit vulnerability check
   - **Infrastructure**: Trivy filesystem scan

5. **Docker Build**:
   - Validates Dockerfile
   - Caches layers
   - Runs on main builds

6. **Container Security**:
   - Trivy image scanning
   - Reports to GitHub Security tab
   - Detects vulnerabilities

7. **Documentation**:
   - Markdownlint validation
   - Codespell typo detection

8. **Status Check**:
   - Aggregates all results
   - Clear pass/fail status

### Workflow File

`.github/workflows/ci-cd.yml` - Complete pipeline

### Usage

```yaml
# Automatically runs on:
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
```

### Key Features

- **Concurrency**: Cancels old runs when new commit pushed
- **Matrix Testing**: Tests on multiple Python versions
- **Caching**: Pip cache for faster builds
- **Services**: PostgreSQL for database tests
- **Artifacts**: Uploads test results and reports
- **Continue on Error**: Non-critical checks don't block

---

## Implementation Summary

### Files Added

```
.github/workflows/
  └── ci-cd.yml                    # Comprehensive CI/CD pipeline

.vscode/
  ├── settings.json                # Team development settings
  ├── extensions.json              # Recommended extensions
  └── launch.json                  # Debug configurations

ai_devops_assistant/
  ├── services/
  │   ├── model_registry.py        # LLM registry integration
  │   └── multi_llm.py             # Multi-provider LLM support
  ├── rag/
  │   └── scraper.py               # Website scraping pipeline
  ├── ml/
  │   ├── __init__.py
  │   └── finetuning.py            # Local LLM fine-tuning
  └── agents/
      └── prompt_manager.py        # Prompt versioning & management

prompts/
  ├── README.md
  ├── system/
  │   └── devops_assistant.md      # Main system prompt
  └── [other categories]

.pre-commit-config.yaml            # Enhanced pre-commit hooks
.markdownlint.json                 # Markdown linting rules
.codespellrc                        # Spell check configuration
.env.example                        # Updated with new options
```

### Files Modified

```
pyproject.toml                      # Added dev dependencies & configs
requirements.txt                    # Added new packages
README.md                           # This comprehensive guide
.vscode/settings.json               # Enhanced development config
.vscode/extensions.json             # Expanded recommendations
.pre-commit-config.yaml             # More comprehensive hooks
```

---

## Production Readiness Checklist

✅ **Code Quality**

- Linting (Ruff)
- Formatting (Black, isort)
- Type checking (MyPy)

✅ **Security**

- SAST scanning (Bandit)
- SCA scanning (pip-audit)
- Container scanning (Trivy)
- Environment security (no secrets in code)

✅ **Testing**

- Unit tests with coverage
- Integration tests
- Multi-version testing (3.11, 3.12)

✅ **Documentation**

- Markdown linting
- Spell checking (codespell)
- Prompt versioning

✅ **Development Experience**

- Pre-commit hooks
- VS Code configuration
- Debugging setup
- Multi-LLM support

✅ **Observability**

- Structured JSON logging
- Request tracing capability
- Error tracking

---

## Next Steps

1. **Run pre-commit setup**: `pre-commit install`
2. **Install dev dependencies**: `pip install -e ".[dev]"`
3. **Copy .env template**: `cp .env.example .env`
4. **Run tests locally**: `pytest tests/`
5. **Review CI pipeline**: `.github/workflows/ci-cd.yml`

## Helm Reliability Update

The Helm chart now includes missing runtime resources and safer deployment behavior without removing kubectl support:

- Added `ServiceAccount` template so the deployment's `serviceAccountName` always resolves.
- Added optional Chroma PVC template and fallback to `emptyDir` when persistence is disabled.
- Added `infra/kubernetes/helm/deploy.sh` with error handling (`lint`, `template`, `--rollback-on-failure --wait`, and automatic diagnostics on failure).

Recommended command:

```bash
./infra/kubernetes/helm/deploy.sh ai-devops-assistant ai-devops-assistant values.yaml
```

---
