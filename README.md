# AI DevOps Copilot

An intelligent AI-powered DevOps assistant that analyzes logs, queries infrastructure, and provides expert recommendations using local LLMs and advanced tool-calling capabilities.

## 🎯 Features

### Core Capabilities

- **📊 DevOps Chat Interface**: Ask questions naturally, get intelligent responses
- **📝 Log Analysis**: Search and analyze application and pipeline logs
- **☸️ Kubernetes Integration**: Query cluster status, pods, deployments, and services
- **💾 SQL Database Queries**: Execute safe SELECT queries to analyze data
- **📈 Prometheus Metrics**: Query system and application metrics
- **📚 RAG Knowledge Base**: Access DevOps best practices and documentation
- **🔄 CI/CD Pipeline Status**: Check build and deployment status

### Example Queries

```
"Why did my pipeline fail?"
"Show me failing pods in the default namespace"
"Which services have the most errors today?"
"Explain this error: OOMKilled"
"What are Kubernetes best practices?"
"Query the database for errors in the last hour"
```

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       FastAPI Backend                            │
│  (REST API, async request handling)                             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
         ▼                 ▼                 ▼
    ┌─────────┐      ┌──────────┐    ┌─────────────┐
    │  Agent  │      │LLM/Ollama│    │  Tool Layer │
    │ Manager │      │ (llama3/ │    │  (Executor) │
    │         │      │ mistral) │    │             │
    └────┬────┘      └──────────┘    └─────┬───────┘
         │                                   │
         ├──────────────────────────────────┤
         │                                  │
    ┌────▼─────────────────────────────┐   │
    │      Tool Registry & Implementations│   │
    │  K8s  SQL  Logs  Metrics  Pipeline  │   │
    └────┬─────────────────────────────┘   │
         │                                  │
    ┌────▼──────┬────────────┬────────┴───┐
    │ PostgreSQL│  Chroma    │ External  │
    │ (Metadata)│  (Vectors) │  Services │
    └───────────┴────────────┴───────────┘
```

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for local development)
- 8GB+ RAM (for running Ollama)

### Option 1: Docker Compose (Recommended)

1. Clone the repository:

```bash
git clone https://github.com/yourusername/ai-devops-copilot.git
cd ai-devops-copilot
```

2. Create environment file:

```bash
cp .env.example .env
```

3. Start all services:

```bash
docker-compose up -d
```

4. Pull the LLM model:

```bash
docker exec ai-devops-copilot-ollama ollama pull llama3
```

5. Access the application:

- FastAPI Backend: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Grafana: http://localhost:3000 (admin/admin)
- Prometheus: http://localhost:9090

### Option 2: Local Development

1. Create and activate virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
pip install -e ".[dev]"
```

3. Set up environment:

```bash
cp .env.example .env
# Edit .env with your local settings
```

4. Initialize database:

```bash
# Run migrations with Alembic
alembic upgrade head
```

5. Start the server:

```bash
uvicorn ai_devops_copilot.main:app --reload
```

## 📖 Usage

### Chat API

```bash
# Start a chat session
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Show me failing pods",
    "session_id": "my-session-1"
  }'
```

### Response Format

```json
{
  "session_id": "my-session-1",
  "message": "I found 2 failing pods in the default namespace...",
  "tool_calls": [
    {
      "tool_name": "kubernetes_tool",
      "parameters": {"action": "list_pods"},
      "result": {...}
    }
  ]
}
```

### Query Log Analysis

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Show me errors from the last 2 hours"
  }'
```

### Access Session History

```bash
curl http://localhost:8000/chat/sessions/{session_id}
```

## 🔧 Configuration

### Environment Variables

```bash
# LLM
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=llama3
LLM_TEMPERATURE=0.7

# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost/copilot

# Kubernetes
KUBECONFIG=/path/to/kubeconfig
K8S_NAMESPACE=default

# Monitoring
PROMETHEUS_URL=http://localhost:9090

# RAG
ENABLE_RAG=true
```

## 🛠️ Development

### Code Quality

```bash
# Run linting
ruff check ai_devops_copilot/

# Format code
black ai_devops_copilot/

# Type checking
mypy ai_devops_copilot/

# Run tests
pytest tests/ -v
```

### Pre-commit Hooks

```bash
# Install pre-commit
pre-commit install

# Run manually
pre-commit run --all-files
```

### Running Tests

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# With coverage
pytest --cov=ai_devops_copilot tests/
```

## 📊 Monitoring

### Prometheus Metrics

The application exposes Prometheus metrics at `/metrics`. Grafana dashboards are pre-configured.

Key metrics:
- `http_requests_total` - Total HTTP requests
- `http_request_duration_seconds` - Request latency
- `llm_queries_total` - LLM API calls
- `tool_executions_total` - Tool executions
- `tool_errors_total` - Tool errors

### Logs

Logs are output in JSON format to stdout for easy parsing and aggregation.

```json
{
  "timestamp": "2024-04-22T10:00:00",
  "level": "INFO",
  "logger": "ai_devops_copilot.agents.agent",
  "message": "Processing chat request for session: abc123"
}
```

## 🐳 Docker

### Build Image

```bash
docker build -t ai-devops-copilot:latest .
```

### Run Container

```bash
docker run -p 8000:8000 \
  -e DATABASE_URL=postgresql+asyncpg://user:password@postgres:5432/copilot \
  -e OLLAMA_BASE_URL=http://ollama:11434 \
  ai-devops-copilot:latest
```

## ☸️ Kubernetes Deployment

See [infra/kubernetes/README.md](infra/kubernetes/README.md) for full deployment instructions.

Quick start:

```bash
# Create namespace
kubectl create namespace copilot

# Apply manifests
kubectl apply -f infra/kubernetes/

# Check status
kubectl get pods -n copilot
```

## 🔐 Security

- SQL queries are validated against injection attacks
- Only SELECT queries allowed
- LLM prompts are carefully engineered to prevent injection
- All sensitive data in environment variables
- No credentials in code

## 🧪 Testing Examples

### Example 1: Kubernetes Pod Query

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "List all pods in the default namespace"
  }'
```

### Example 2: Log Analysis

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Find ERROR logs from the last 24 hours"
  }'
```

### Example 3: Metrics Query

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is the current request latency?"
  }'
```

## 📚 Documentation

- [Architecture](ARCHITECTURE.md) - System design and components
- [Implementation Plan](IMPLEMENTATION_PLAN.md) - Development roadmap
- [API Reference](docs/API.md) - REST API documentation
- [Contributing](docs/CONTRIBUTING.md) - Contribution guidelines

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](docs/CONTRIBUTING.md) for guidelines.

## 📝 License

MIT License - see [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [LangChain](https://python.langchain.com/) - AI/ML orchestration
- [Ollama](https://ollama.ai/) - Local LLMs
- [Chroma](https://www.trychroma.com/) - Vector database
- [Kubernetes Python Client](https://github.com/kubernetes-client/python)
- [Prometheus Python Client](https://github.com/prometheus/client_python)

## 📞 Support

- 🐛 Report bugs: [GitHub Issues](https://github.com/yourusername/ai-devops-copilot/issues)
- 💬 Discussions: [GitHub Discussions](https://github.com/yourusername/ai-devops-copilot/discussions)
- 📧 Email: devops@example.com

---

**Happy DevOps-ing!** 🚀
