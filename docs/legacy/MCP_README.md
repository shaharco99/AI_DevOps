# RAG Agent - Complete System Documentation

A comprehensive DevOps AI assistant system combining Agentic RAG, database integration, document analysis, and multi-interface support.

**Key Capabilities:**
- 🤖 **Agentic RAG**: Autonomous query routing with self-reflection & iterative refinement
- 🔀 **Hybrid Routing**: SQL for numeric queries, Vector search for documentation, both when needed
- 🗄️ **Database Integration**: Multi-database support with natural language to SQL conversion
- 📄 **Document Analysis**: RAG with ChromaDB semantic search and automatic chunking
- 💬 **Multi-Interface**: Chat, CLI, GUI, and Unified agent modes
- 🧠 **Self-Reflection**: Automatic response quality evaluation with iterative improvement
- 🛡️ **Safety First**: SELECT-only enforcement, SQL injection prevention, user approval workflows
- 🔧 **Tool Integration**: LangChain tools with automatic execution chains

## 🚀 Quick Start

### Option 1: Database Query (Recommended for New Users)
```bash
python quick_start_database.py
python unified_interface.py
# Then ask: "Show me all customers from the USA"
```

### Option 2: Interactive Chat Mode
```bash
python unified_interface.py
```

### Option 3: Command-Line Execution
```bash
python unified_interface.py --prompt "Your question here"
```

### Option 4: Graphical Interface
```bash
python unified_interface.py --gui
```

### Option 5: Agentic RAG Pipeline
```bash
python unified_interface.py --rag --query "Your question"
```

---

# Table of Contents

1. [Core Features](#core-features)
2. [System Architecture](#system-architecture)
3. [Unified Interface](#unified-interface---multi-mode-entry-point)
4. [Database Query Feature](#database-query-feature)
5. [RAG System](#rag-retrieval-augmented-generation)
6. [Testing](#testing)
7. [Performance & Optimization](#performance--optimization)
8. [Support & Resources](#support--resources)

---

# Core Features

## 🤖 Agentic RAG with Self-Reflection

The system implements a sophisticated agentic RAG pipeline:

### Query Router
- **Intelligent analysis**: Automatically determines optimal retrieval strategy
- **Routing strategies**:
  - `SQL_ONLY` - Database queries for numeric/analytical questions
  - `VECTOR_ONLY` - Vector search for policy/documentation questions
  - `HYBRID` - Combined SQL and vector retrieval
  - `NO_RETRIEVAL` - General conversation requiring no data access

### Self-Reflection Loop
- **Quality evaluation**: Automatically assesses response quality
- **Iterative refinement**: Improves responses through feedback loops (up to 3 iterations)
- **Feedback types**:
  - `SUFFICIENT` - Response is complete and accurate
  - `NEEDS_MORE_CONTEXT` - Needs additional data
  - `NEEDS_REFINEMENT` - Response needs improvement
  - `CONTRADICTORY` - Response contains conflicts

### Vector Retrieval
- **ChromaDB integration**: Semantic similarity search
- **Document indexing**: Automatic chunking and embedding
- **Top-K retrieval**: Configurable result count
- **Metadata tracking**: Source and context preservation

## 🗄️ Database Integration

### Multi-Database Support
- **SQLite** - Default, file-based, no setup required
- **PostgreSQL** - Enterprise-grade, ACID compliant
- **MySQL** - Fast, scalable, widely supported
- **MSSQL** - SQL Server support with ODBC

### Safe Query Execution
- **SELECT-only enforcement** - No INSERT, UPDATE, DELETE, DDL
- **Auto-correction** - Fuzzy matching for table/column names
- **Injection prevention** - SQL injection protection
- **Schema validation** - Query validation before execution
- **User approval** - Preview and confirm before execution

### Natural Language to SQL
- **Question understanding** - Parses business language
- **Query generation** - Creates appropriate SQL automatically
- **Smart joins** - Understands table relationships
- **Aggregations** - GROUP BY, COUNT, SUM, AVG, MAX, MIN

## 📄 Document Analysis

### Supported File Formats
- **Documents**: PDF, DOCX (Word), PPTX (PowerPoint)
- **Data**: CSV, JSON, XLSX (Excel)
- **Web**: HTML, HTM
- **Text**: TXT, MD (Markdown)

### RAG Capabilities
- **Automatic chunking** - Sentence-aware document splitting
- **Vector embeddings** - Semantic understanding
- **Similarity search** - Find relevant context
- **Metadata tracking** - Source and origin preservation

## 🧠 Memory Management
- **Conversation history** - Full chat context preservation
- **Tool integration** - Chainable tool execution
- **State management** - Maintains query results across interactions

---

# System Architecture

## Component Overview

```
┌─────────────────────────────────────────────────────┐
│         Unified Interface (unified_interface.py)    │
│    Chat | CLI | RAG | GUI                          │
└────────────┬────────────────────────────────────────┘
             │
     ┌───────┴─────────┐
     │                 │
     v                 v
┌──────────────┐  ┌──────────────────┐
│  Chat.py     │  │  unified_agent.py│
│  (CLI Mode)  │  │ (Unified Agent)  │
└──────────────┘  └────────┬─────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        v                  v                  v
    ┌────────────┐  ┌────────────┐  ┌──────────────┐
    │QueryRouter │  │Reflection  │  │Vector        │
    │(Routing)   │  │Agent       │  │Retriever     │
    │            │  │(Quality)   │  │(ChromaDB)    │
    └────────────┘  └────────────┘  └──────────────┘
        │
        └─────────────────┬──────────────────┐
                          │                  │
                          v                  v
                    ┌──────────────┐  ┌──────────────┐
                    │Database      │  │LangChain     │
                    │Tools         │  │Agent         │
                    │(Safe SQL)    │  │(Tools)       │
                    └──────────────┘  └──────────────┘
```

## Key Classes and Methods

### QueryRouteType (Enum)
Routing strategies for query processing:
- `SQL_ONLY` - Database queries (numeric, analytical)
- `VECTOR_ONLY` - Vector search (policy, documentation)
- `HYBRID` - Combined SQL and vector retrieval
- `NO_RETRIEVAL` - General conversation

### ReflectionFeedback (Enum)
Self-reflection feedback types:
- `SUFFICIENT` - Response is adequate
- `NEEDS_MORE_CONTEXT` - Needs additional information
- `NEEDS_REFINEMENT` - Quality can be improved
- `CONTRADICTORY` - Contains conflicts

### UnifiedAgent (Main Class)

**Initialization:**
```python
agent = UnifiedAgent(
    base_url='http://localhost:11434',
    model='gpt-oss:latest',
    collection_name='rag_collection',
    db_path='sample_database.db',
    max_reflection_iterations=3
)
```

**Key Methods:**
- `run(query)` - Main entry point for query processing
- `add_tool(name, func, description)` - Register custom tools
- `initialize_agent()` - Setup LangChain agent

**Return Value from run():**
```python
{
    'status': 'success' | 'error',
    'result': str | None,
    'error': str | None,
    'routing_strategy': str,
    'routing_confidence': float,
    'retrieval_used': dict,
    'reflection_feedback': str | None
}
```

### QueryRouter

**Purpose:** Intelligent query analysis and routing

**Method:**
```python
analysis = router.analyze(query: str) -> QueryAnalysis
# Returns: route_type, confidence, reasoning, should_retrieve_sql, should_retrieve_vector
```

### ReflectionAgent

**Purpose:** Response quality evaluation and iterative refinement

**Method:**
```python
reflection = reflector.reflect(
    query: str,
    response: str,
    sql_results_available: bool = False,
    vector_results_available: bool = False,
    iterations: int = 1
) -> ReflectionResult
```

### VectorRetriever

**Purpose:** ChromaDB semantic search wrapper

**Method:**
```python
docs = retriever.retrieve(
    query: str,
    top_k: int = 5,
    similarity_threshold: float = 0.5
) -> List[Dict]
```

### DatabaseTools

**Purpose:** Safe SQL execution with validation and auto-correction

**Methods:**
- `execute_query(query)` - Execute SELECT query
- `validate_query(query)` - Check query safety
- `get_schema()` - Get database structure

---

# Unified Interface - Multi-Mode Entry Point

The `unified_interface.py` is the primary entry point for all interaction modes. It provides a single interface to access Chat, CLI, GUI, and RAG modes.

## Usage

### Interactive Chat Mode (Default)
```bash
python unified_interface.py
```
Starts an interactive conversation loop where you can:
- Ask questions about databases, documents, or general topics
- Load and analyze files
- Chain multiple queries together
- Exit with 'exit', 'quit', or Ctrl+C

**Example:**
```
You: Load data.csv
AI: [Analyzes file]
You: How many rows?
AI: The file contains 1,500 rows
You: Show me the first 5 columns
AI: [Displays results]
```

### Command-Line Mode
```bash
python unified_interface.py --prompt "Your question"
```

**With prompt file:**
```bash
python unified_interface.py --prompt-file ./prompt.txt
```

**With verbose output:**
```bash
python unified_interface.py --prompt "Load data.csv" --verbose
```

### Graphical Interface Mode
```bash
python unified_interface.py --gui
```

Features:
- Interactive GUI with Tkinter
- File upload button
- Real-time conversation history
- Result display and formatting

### Agentic RAG Mode
```bash
python unified_interface.py --rag --query "Your question"
```

Explicitly uses the Agentic RAG pipeline with:
- Intelligent query routing
- Self-reflection and iterative refinement
- Hybrid SQL and vector retrieval
- Multi-step tool execution

## Command-Line Options

```
usage: unified_interface.py [-h] [--prompt PROMPT] [--prompt-file FILE]
                            [--verbose] [--gui] [--rag]
                            [--query QUERY]

optional arguments:
  -h, --help              Show this help message
  --prompt PROMPT         Direct prompt text to execute
  --prompt-file FILE      Path to file containing the prompt
  --verbose, -v           Show tool execution details
  --gui                   Launch graphical interface
  --rag                   Use agentic RAG pipeline
  --query QUERY          Query for RAG mode
```

## Features Across All Modes

### Document Loading
- **Supported formats**: PDF, DOCX, PPTX, CSV, JSON, XLSX, HTML, TXT, MD
- **Automatic detection**: File type detected automatically
- **Integration**: Works seamlessly across all modes

### Database Integration
- **Natural language queries**: Ask questions about your data
- **Multi-database support**: SQLite, PostgreSQL, MySQL, MSSQL
- **Safe execution**: SELECT-only with auto-correction
- **PDF export**: Generate reports from query results

### RAG Capabilities
- **Semantic search**: Find relevant documents by meaning
- **Vector retrieval**: ChromaDB integration
- **Automatic chunking**: Smart document splitting
- **Context injection**: Relevant information added to responses

### Tool Integration
- **Multi-step chains**: Execute sequences of tools
- **Smart selection**: Choose appropriate tools automatically
- **Error handling**: Graceful fallbacks for missing tools
- **Custom tools**: Add your own functions

## Configuration

Create `.env` file in project root or `LLM_CI/` directory:

```bash
# LLM Provider
LLM_PROVIDER=OLLAMA
OLLAMA_MODEL=gpt-oss:latest

# Optional: For other providers
# OPENAI_API_KEY=your_key
# GOOGLE_API_KEY=your_key
# ANTHROPIC_API_KEY=your_key

# Database
DB_TYPE=sqlite
DB_PATH=database.db

# RAG
VAULT_FILE=LLM_CI/vault.txt
CHROMA_COLLECTION=rag_collection
```

See `LLM_CI/.env.template` for all available options.

## Implementation Details

The `unified_interface.py` (450+ lines) orchestrates:

**Chat Mode** (`Chat.py`):
- Interactive conversation loop
- Tool execution chains
- Multi-LLM support
- Memory management

**CLI Mode** (`cli.py`):
- Single prompt execution
- Piping and redirection
- File-based prompts
- Exit codes

**GUI Mode** (`ChatGUI.py`):
- Graphical Tkinter interface
- File upload integration
- Conversation history
- Real-time display

**RAG Mode** (`unified_agent.py`):
- Query routing analysis
- Self-reflection loop
- Hybrid retrieval
- Tool orchestration


---

# Database Query Feature

Ask natural language questions about your database, and the unified interface will:

1. **Understand the question** - Parse what data you're looking for
2. **Generate SQL** - Create appropriate SQL query
3. **Get approval** - Show query and ask for confirmation
4. **Execute safely** - Run with safety checks preventing dangerous operations
5. **Display results** - Show results in formatted table
6. **Export to PDF** - Optionally generate professional report

## Quick Start

```bash
python quick_start_database.py
python unified_interface.py
# Then ask: "Show me all customers from the USA"
```

## Database Configuration

Create `LLM_CI/db_config.json`:

**SQLite** (default):
```json
{
  "type": "sqlite",
  "database": "database.db"
}
```

**PostgreSQL**:
```json
{
  "type": "postgresql",
  "host": "localhost",
  "port": 5432,
  "user": "postgres",
  "password": "your_password",
  "database": "your_database"
}
```

**MySQL**:
```json
{
  "type": "mysql",
  "host": "localhost",
  "port": 3306,
  "user": "root",
  "password": "your_password",
  "database": "your_database"
}
```

## Example Queries

**Simple selection:**
```
You: Show me all customers from the USA
```

**Aggregation:**
```
You: How many orders did each customer place?
```

**Complex:**
```
You: Show me orders from 2023 over $500 sorted by date
```

## Safety Features

Protected operations (blocked):
- `DROP` - Database/table deletion
- `TRUNCATE` - Table clearing
- `DELETE` - Data deletion
- `ALTER` - Schema modification
- `CREATE` - Table/database creation

---

# RAG (Retrieval-Augmented Generation)

Access local document vault for context-aware responses using ChromaDB vector search.

## Quick Start

```bash
# Optional: Set docs directory
export RAG_DOCS_DIR=/path/to/your/docs

# Start unified interface
python unified_interface.py

# In chat:
# You: Upload all documents from docs/
# You: What's our remote work policy?
```

## Features

- **Semantic search**: Find relevant documents by meaning
- **Automatic chunking**: Smart sentence-aware splitting
- **Vector embeddings**: ChromaDB integration
- **Context injection**: Relevant information added automatically
- **Offline support**: Falls back to deterministic embedding if needed

## Environment Variables

- `VAULT_FILE` - Path to vault file (default: `LLM_CI/vault.txt`)
- `RAG_DOCS_DIR` or `VAULT_DIR` - Folder to preload at startup
- `CHROMA_COLLECTION` - Collection name (default: `rag_collection`)
- `OLLAMA_EMBED_MODEL` - Ollama embedding model
- `OPENAI_EMBED_MODEL` - OpenAI embedding model

---

# Project Structure

```
/home/shahar/repos/MCP/
├── README.md                           # Complete documentation (this file)
├── requirements.txt                    # Python dependencies
├── pyproject.toml                      # Project configuration
├── unified_agent.py                    # Main agent implementation (550 lines)
├── unified_interface.py                # Multi-mode interface (450 lines)
├── quick_start_database.py             # Sample database setup
├── LLM_CI/
│   ├── Chat.py                         # Interactive chat interface
│   ├── ChatGUI.py                      # Graphical interface
│   ├── cli.py                          # Command-line interface
│   ├── Utils.py                        # LLM provider utilities & RAG
│   ├── Tools.py                        # Tool definitions
│   ├── database_tools.py               # Database functionality
│   ├── pdf_generator.py                # PDF export
│   ├── query_confirmation.py           # Query approval workflow
│   ├── vault.txt                       # Document vault for RAG
│   ├── db_config.template.json         # Database config template
│   └── .env.template                   # Environment configuration template
├── tests/
│   ├── test_unified_agent.py           # Agent tests (29/29 passing) ✅
│   ├── test_database_tools.py          # Database tests
│   ├── test_rag.py                     # RAG system tests
│   └── additional test files
├── logs/                               # Application logs
├── query_results/                      # PDF exports
└── MCP/
    ├── server.py                       # MCP server (optional)
    ├── agents.py                       # Agent definitions
    └── configuration files
```

---

# Core Files

## Implementation Files

| File | Purpose | Lines |
|------|---------|-------|
| `unified_agent.py` | Main agent with routing, reflection, retrieval | 550+ |
| `unified_interface.py` | Multi-mode interface (Chat/CLI/RAG/GUI) | 450+ |
| `LLM_CI/Utils.py` | LLM providers, RAG, utilities | 826 |
| `LLM_CI/Tools.py` | Tool definitions and execution | 300+ |
| `LLM_CI/database_tools.py` | Database connections, queries, validation | 400+ |
| `LLM_CI/Chat.py` | Interactive chat loop | 200+ |
| `LLM_CI/cli.py` | Command-line interface | 150+ |
| `LLM_CI/ChatGUI.py` | GUI with Tkinter | 300+ |

## Test Files

| File | Tests | Status |
|------|-------|--------|
| `tests/test_unified_agent.py` | 29 tests | ✅ All passing |
| `tests/test_database_tools.py` | 10+ tests | ✅ Passing |
| `tests/test_rag.py` | 5+ tests | ✅ Passing |

---

# System Components Explained

## QueryRouter

Analyzes queries and determines optimal retrieval strategy:

```python
from unified_agent import QueryRouter
from langchain_ollama import OllamaLLM

llm = OllamaLLM(model="gpt-oss:latest")
router = QueryRouter(llm)

analysis = router.analyze("How many customers from USA?")
# Returns: SQL_ONLY routing with 95% confidence
```

**Routing Decisions:**
- Numeric questions → SQL_ONLY
- Policy/documentation questions → VECTOR_ONLY  
- Mixed questions → HYBRID
- Conversational → NO_RETRIEVAL

## ReflectionAgent

Evaluates response quality and suggests improvements:

```python
from unified_agent import ReflectionAgent

reflector = ReflectionAgent(llm)

reflection = reflector.reflect(
    query="How many employees in sales?",
    response="There are 25 employees.",
    sql_results_available=True
)

if reflection.requires_refinement:
    print(f"Action: {reflection.suggested_action}")
```

**Feedback Types:**
- SUFFICIENT - No refinement needed
- NEEDS_MORE_CONTEXT - Add more data
- NEEDS_REFINEMENT - Improve quality
- CONTRADICTORY - Fix conflicts

## VectorRetriever

ChromaDB semantic search:

```python
from unified_agent import VectorRetriever

retriever = VectorRetriever(collection_name="company_docs")

docs = retriever.retrieve(
    query="remote work policy",
    top_k=5,
    similarity_threshold=0.5
)

for doc in docs:
    print(f"{doc['content']} (Source: {doc['source']})")
```

## DatabaseTools

Safe SQL execution:

```python
from unified_agent import DatabaseTools

db = DatabaseTools(db_path="company.db")

# Get schema
schema = db.get_schema()

# Validate query
valid, msg = db.validate_query("SELECT * FROM employees")

# Execute safely
results, error = db.execute_query("SELECT * FROM employees WHERE salary > 50000")
```

## UnifiedAgent

Main orchestrator:

```python
from unified_agent import UnifiedAgent
import asyncio

async def main():
    agent = UnifiedAgent()
    
    # Add custom tool
    def get_weather(location: str) -> str:
        return "Sunny, 72°F"
    
    agent.add_tool("get_weather", get_weather, "Get current weather")
    
    # Run query
    result = await agent.run("How many customers in USA and what's the weather in NYC?")
    
    print(f"Response: {result['result']}")
    print(f"Method: {result['routing_strategy']}")

asyncio.run(main())
```

---

# Common Use Cases

## Use Case 1: Business Analytics

```
User: Show me the top 5 customers by total purchase amount
Agent: Detects SQL_ONLY route → Generates JOIN query → Executes → Returns results
User: Export to PDF
Agent: Creates PDF with formatted results
```

## Use Case 2: Policy Lookup

```
User: What's our remote work policy?
Agent: Detects VECTOR_ONLY route → Retrieves policy documents → Provides answer
User: What about parental leave?
Agent: Retrieves from same documents → Answers follow-up
```

## Use Case 3: Complex Hybrid Query

```
User: How many engineers are in NYC and what's their training budget?
Agent: Detects HYBRID route → SQL: employees in NYC → Vector: training budget policy
Agent: Combines both → Provides complete answer
```

## Use Case 4: Document Analysis

```
User: Load and summarize the quarterly report
Agent: Uses doc_loader → Retrieves document → Analyzes → Provides summary
User: What were the key metrics?
Agent: Extracts metrics from vault → Provides structured answer
```

---

# Integration Examples

## Using in Python Code

```python
import asyncio
from unified_agent import UnifiedAgent

async def analyze_data():
    agent = UnifiedAgent(db_path="mydata.db")
    
    result = await agent.run(
        "Show me revenue by region for Q4 2023"
    )
    
    if result['status'] == 'success':
        print(result['result'])
        print(f"Used: {result['routing_strategy']}")
    else:
        print(f"Error: {result['error']}")

asyncio.run(analyze_data())
```

## Using in Bash Scripts

```bash
#!/bin/bash

# Ask a question via CLI
python LLM_CI/cli.py --prompt "Show me customers from California" > results.txt

# Process results
if [ -s results.txt ]; then
    echo "Query successful"
    cat results.txt
fi
```

## Using as Chat Bot

```bash
# Start interactive chat
python LLM_CI/Chat.py

# Then interact:
# You: Load data.csv
# AI: [Loads file and analyzes]
# You: How many records?
# AI: [Returns count]
```

---

# Testing

## Run All Tests

```bash
cd /home/shahar/repos/MCP
pytest tests/ -v
```

## Run Specific Test

```bash
pytest tests/test_unified_agent.py::test_query_router_analyze -v
```

## Run with Coverage

```bash
pytest tests/ --cov=. --cov-report=html
```

## Test Results

```
test_unified_agent.py::test_query_router_json_extraction PASSED
test_unified_agent.py::test_query_router_analyze_sql_only PASSED
test_unified_agent.py::test_query_router_analyze_vector_only PASSED
test_unified_agent.py::test_query_router_analyze_hybrid PASSED
test_unified_agent.py::test_reflection_agent_sufficient PASSED
test_unified_agent.py::test_reflection_agent_needs_refinement PASSED
test_unified_agent.py::test_vector_retriever_retrieve PASSED
test_unified_agent.py::test_database_tools_initialization PASSED
test_unified_agent.py::test_database_tools_select_only PASSED
test_unified_agent.py::test_unified_agent_initialization PASSED
test_unified_agent.py::test_unified_agent_add_tool PASSED
...
[29/29 tests PASSED] ✅
```

---

# Performance & Optimization

## Reflection Iterations

```python
# For critical queries (better quality)
agent = UnifiedAgent(max_reflection_iterations=5)

# For speed (default)
agent = UnifiedAgent(max_reflection_iterations=3)

# For real-time responses
agent = UnifiedAgent(max_reflection_iterations=1)
```

## Vector Retrieval

```python
# Get more results
docs = retriever.retrieve(query, top_k=10)

# Get fewer results
docs = retriever.retrieve(query, top_k=3)

# Adjust similarity threshold
docs = retriever.retrieve(query, similarity_threshold=0.7)
```

## Database Optimization

- SQLite: Good for dev/small data
- PostgreSQL: Recommended for production
- MySQL: Good for web apps
- Use proper indexes on frequently queried columns
- Cache schema after database structure changes

---

# License & Credits

This comprehensive system was built by integrating:
- LangChain for LLM orchestration
- ChromaDB for vector storage
- SQLAlchemy for database abstraction
- ReportLab for PDF generation
- Multiple LLM providers (Ollama, OpenAI, Google, Anthropic)

---

# Support & Resources

- **Documentation**: All comprehensive guides merged into this README
- **Code Examples**: Throughout this document
- **Tests**: 29 passing tests in `tests/test_unified_agent.py`
- **Logs**: Check `logs/` directory for detailed execution logs

---

# Next Steps

1. **Install**: `pip install -r requirements/dev.txt`
2. **Configure**: Create `.env` file with your LLM provider
3. **Setup Database** (optional): `python quick_start_database.py`
4. **Start Using**: `python LLM_CI/Chat.py`
5. **Explore**: Try different modes and features
6. **Integrate**: Use `UnifiedAgent` in your own code

## Security
- `run_shell` is intentionally whitelisted and rejects pipes/redirections. Do not expand without considering risk.
