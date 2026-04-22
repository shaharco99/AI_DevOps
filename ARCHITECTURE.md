# AI DevOps Assistant - Architecture Design Document

## Executive Summary

The AI DevOps Assistant is a production-grade system that combines AI, DevOps tooling, and observability to provide intelligent assistance for DevOps engineers. It uses an agentic AI system with tool-calling capabilities to analyze logs, query infrastructure, and provide recommendations.

---

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                       Client / Frontend                          │
│                     (Chat Interface Layer)                       │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP/WebSocket
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend Server                        │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │           REST API Endpoints                              │ │
│  │  /chat  /run_sql  /analyze_logs  /metrics  /health       │ │
│  └────────────────────────────────────────────────────────────┘ │
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
         │           ┌───────────────────────┼───────────────┐
         │           │                       │               │
         ▼           ▼                       ▼               ▼
    ┌─────────────────────────────────────────────────────────────┐
    │              Tool Registry & Implementations                │
    │  ┌────────────┐ ┌────────────┐ ┌────────────┐              │
    │  │   K8s Tool │ │  SQL Tool  │ │  Log Tool  │              │
    │  └────────────┘ └────────────┘ └────────────┘              │
    │  ┌────────────┐ ┌────────────┐ ┌────────────┐              │
    │  │  RAG Tool  │ │ Metrics Tool│ │Pipeline Tool             │
    │  └────────────┘ └────────────┘ └────────────┘              │
    └────────────────────────────────────────────────────────────┘
         │                 │                 │
    ┌────▼──────┐    ┌────▼──────┐    ┌────▼──────┐
    │ PostgreSQL │    │  Chroma   │    │  External │
    │ (Metadata) │    │  (Vector  │    │  Services │
    │            │    │   DB)     │    │ (K8s, Prom)
    └────────────┘    └───────────┘    └───────────┘
```

---

## Core Components

### 1. **FastAPI Application Core**
- RESTful API server
- Request/response handling
- Authentication & authorization
- Error handling and logging

### 2. **LangChain Agent System**
- Tool-calling agent orchestration
- Multi-turn conversation support
- Memory management
- Tool execution chain

### 3. **LLM Integration (Ollama)**
- Local LLM inference
- Model management
- Prompt engineering
- Token optimization

### 4. **Tool Layer**
- Kubernetes query tool
- SQL query tool
- Log analysis tool
- Pipeline status tool
- Metrics query tool
- RAG retrieval tool

### 5. **RAG System**
- Document ingestion
- Embedding generation
- Vector storage (Chroma)
- Semantic search

### 6. **Data Layer**
- PostgreSQL for structured data
- Vector database for embeddings
- Connection pooling
- Query optimization

### 7. **Observability**
- Prometheus metrics
- Grafana dashboards
- Application logging
- Performance monitoring

---

## Data Flow

### Chat Request Flow

```
1. User sends question via /chat endpoint
   ├─ Request validation
   ├─ Session/context loading
   │
2. LangChain Agent receives query
   ├─ Parse intent
   ├─ Determine required tools
   │
3. Agent calls LLM for tool selection
   ├─ Pass available tools
   ├─ Get tool name + parameters
   │
4. Tool Executor executes selected tool
   ├─ SQL Tool: Generate & execute SQL safely
   ├─ K8s Tool: Query cluster state
   ├─ Log Tool: Search and analyze logs
   ├─ RAG Tool: Retrieve relevant docs
   ├─ Metrics Tool: Query prometheus
   │
5. Tool results passed back to LLM
   ├─ Format results
   ├─ Add context
   │
6. LLM generates response
   ├─ Synthesize results
   ├─ Format for user
   │
7. Response sent to client
   ├─ Stream or complete
   ├─ Log interaction
```

---

## Technical Stack Details

### Backend
- **Framework**: FastAPI (async, high performance)
- **Language**: Python 3.11+
- **ORM**: SQLAlchemy (async support)
- **Validation**: Pydantic v2

### AI/ML
- **Framework**: LangChain
- **LLM**: Ollama (local inference)
- **Models**: Llama 3 (70B or 8B) or Mistral 7B
- **Embeddings**: sentence-transformers
- **Vector DB**: Chroma (embedded)

### Data
- **Primary DB**: PostgreSQL 15+
- **Vector Store**: Chroma
- **Connection Pool**: asyncpg with connection pooling

### DevOps & Infrastructure
- **Containerization**: Docker & Docker Compose
- **Orchestration**: Kubernetes (optional)
- **Monitoring**: Prometheus + Grafana
- **CI/CD**: GitHub Actions

### Development
- **Linting**: Ruff
- **Formatting**: Black
- **Type Checking**: Mypy
- **Testing**: Pytest
- **Pre-commit**: pre-commit hooks

---

## Module Breakdown

### `ai_devops_assistant/`

#### `agents/`
- `agent.py` - Main LangChain agent orchestration
- `prompts.py` - System prompts and prompt templates
- `memory.py` - Conversation memory management
- `tool_registry.py` - Tool registration and validation

#### `tools/`
- `__init__.py` - Tool factory
- `kubernetes_tool.py` - K8s cluster queries
- `sql_tool.py` - SQL query generation & execution
- `log_tool.py` - Log ingestion and analysis
- `metrics_tool.py` - Prometheus queries
- `pipeline_tool.py` - CI/CD status queries
- `tool_executor.py` - Tool execution engine

#### `rag/`
- `__init__.py` - RAG initialization
- `embeddings.py` - Embedding model setup
- `vector_store.py` - Chroma vector store management
- `document_ingestion.py` - Document loading and processing
- `retriever.py` - Semantic search interface

#### `database/`
- `__init__.py` - Database initialization
- `models.py` - SQLAlchemy models (Pipeline logs, metrics, etc.)
- `session.py` - Async session management
- `migrations.py` - Alembic migrations
- `queries.py` - Common queries

#### `services/`
- `llm_service.py` - Ollama integration
- `log_service.py` - Log ingestion and processing
- `metrics_service.py` - Metrics collection
- `kubernetes_service.py` - K8s API wrapper
- `cache_service.py` - Caching layer

#### `api/`
- `routes/` - API endpoints
  - `chat.py` - Chat endpoint
  - `sql.py` - SQL query endpoint
  - `logs.py` - Log analysis endpoint
  - `metrics.py` - Metrics endpoint
  - `health.py` - Health check endpoint
- `dependencies.py` - Dependency injection
- `schemas.py` - Request/response schemas
- `middleware.py` - Logging, CORS, error handling

#### `config/`
- `settings.py` - Environment configuration
- `constants.py` - Application constants
- `logging.py` - Logging configuration

---

## Database Schema

### Tables

#### `pipeline_logs`
```
id: UUID
pipeline_id: string
run_number: int
status: enum (success, failed, running)
log_content: text
error_summary: text
created_at: timestamp
updated_at: timestamp
```

#### `metric_snapshots`
```
id: UUID
service_name: string
metric_name: string
value: float
timestamp: timestamp
labels: jsonb
```

#### `rag_documents`
```
id: UUID
title: string
content: text
source: string
category: string
embedding_id: string
created_at: timestamp
```

#### `chat_sessions`
```
id: UUID
user_id: string
started_at: timestamp
ended_at: timestamp
message_count: int
```

#### `chat_messages`
```
id: UUID
session_id: UUID (FK)
role: enum (user, assistant)
content: text
tools_used: array
created_at: timestamp
```

---

## Configuration Management

### Environment Variables

```
# LLM Configuration
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=llama3  # or mistral
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=2048

# Database Configuration
DATABASE_URL=postgresql+asyncpg://user:password@localhost/devops
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=40

# Vector DB Configuration
CHROMA_PERSIST_DIR=/data/chroma
CHROMA_ANONYMIZED_TELEMETRY=false

# Kubernetes Configuration
KUBECONFIG=/path/to/kubeconfig
K8S_NAMESPACE=default

# Prometheus Configuration
PROMETHEUS_URL=http://localhost:9090

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_LOG_LEVEL=INFO

# RAG Configuration
RAG_CHUNK_SIZE=1000
RAG_CHUNK_OVERLAP=100
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Security
SECRET_KEY=your-secret-key-here
```

---

## Security Considerations

1. **SQL Injection Prevention**
   - Use SQLAlchemy ORM exclusively
   - No raw query construction from user input
   - Parameterized queries only

2. **LLM Prompt Injection Prevention**
   - Validate tool outputs
   - Sanitize user inputs
   - Use system prompts effectively

3. **Access Control**
   - Environment-based access control
   - API key authentication (future)
   - RBAC for different tools

4. **Data Protection**
   - Encrypt sensitive data in transit
   - Use environment variables for secrets
   - Audit logging for sensitive operations

5. **Rate Limiting**
   - Implement per-user/IP rate limits
   - Tool-specific quotas
   - Backpressure handling

---

## Deployment Scenarios

### Local Development
```
docker-compose up
- PostgreSQL
- Ollama
- Chroma (embedded)
- FastAPI backend
- Prometheus
- Grafana
```

### Production (Kubernetes)
```
- Deployments for FastAPI replicas
- StatefulSet for PostgreSQL
- ConfigMaps for configuration
- Secrets for credentials
- Ingress for external access
- HPA for autoscaling
```

---

## Performance Characteristics

### Expected Latencies

| Operation | Latency |
|-----------|---------|
| Chat response (cold) | 2-5s |
| Chat response (warm) | 500-1500ms |
| SQL query | 100-500ms |
| Log search | 200-800ms |
| RAG retrieval | 300-600ms |
| Metrics query | 100-300ms |

### Scalability

- **Horizontal**: Multiple FastAPI replicas behind load balancer
- **Vertical**: Larger Ollama instances for faster inference
- **Database**: Connection pooling, query optimization, caching
- **Vector DB**: In-process Chroma sufficient for < 100K documents

---

## Monitoring & Observability

### Key Metrics

1. **Agent Metrics**
   - Tool call frequency
   - Tool success/failure rate
   - Agent latency

2. **System Metrics**
   - Request latency
   - Error rate
   - Database connection pool usage
   - LLM token usage

3. **Business Metrics**
   - Chat volume
   - Common questions
   - User satisfaction signals

### Logging Strategy

- Structured logging with JSON format
- Request/response logging
- Tool execution logging
- Error tracking
- Performance metrics

---

## Testing Strategy

### Unit Tests
- Tool implementations
- Database queries
- RAG retrieval
- LLM prompt formatting

### Integration Tests
- Agent end-to-end flows
- Tool-calling chains
- Database transactions
- External service mocks

### E2E Tests
- Full chat scenarios
- Multi-turn conversations
- Error handling flows

---

## Future Enhancements

1. **Multi-model support** - Switch between multiple LLMs
2. **Fine-tuning** - Domain-specific model tuning
3. **Multi-agent collaboration** - Specialized agents
4. **Advanced RAG** - Metadata filtering, reranking
5. **Cost tracking** - Token and compute cost monitoring
6. **Custom tools** - User-defined tool creation
7. **Audit trail** - Compliance logging
8. **Analytics dashboard** - Usage analytics
