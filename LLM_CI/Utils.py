from __future__ import annotations

import getpass
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv(*_, **__):
        return None

try:
    from Tools import code_reviewer, doc_loader
except Exception:
    code_reviewer = None
    doc_loader = None

try:
    from database_tools import (
        execute_database_query,
        get_database_schema_info,
        get_table_preview,
        validate_sql_query,
    )
    DATABASE_TOOLS_AVAILABLE = True
except ImportError:
    DATABASE_TOOLS_AVAILABLE = False
    execute_database_query = None
    get_database_schema_info = None
    get_table_preview = None
    validate_sql_query = None

# Load environment variables
load_dotenv()

# Build optional database tools description depending on availability
db_tools_text = (
    '- **get_database_schema_info**: Get the complete database schema including all tables and their columns.\n'
    '- **get_table_preview**: Get a preview of sample rows from a specific table to understand data structure.\n'
    '- **validate_sql_query**: Validate and auto-correct a SQL SELECT query against the database schema.\n'
    '- **execute_database_query**: Execute SELECT queries directly after validating and auto-correcting them to fit the database schema.\n'
) if DATABASE_TOOLS_AVAILABLE else ''

system_message = f"""
## You are a Comprehensive AI Assistant for DevOps, Data Analysis, and Business Intelligence

You are an expert AI assistant with capabilities spanning multiple domains:

### Your Capabilities

#### 1. Document Analysis & Knowledge Retrieval
- **Load Files**: Use `doc_loader` to load: PDF, TXT, MD, CSV, JSON, HTML, DOCX, PPTX, XLSX
- **Code Review**: Analyze Python files with `code_reviewer` for quality and best practices
- **Knowledge Base**: Access local vault for context-aware responses via ChromaDB vector search
- **Context Awareness**: Retrieve relevant information from document collections automatically

#### 2. Database Query & Analysis
- **Natural Language to SQL**: Convert business questions directly to SQL queries
- **Multi-Database Support**: SQLite, PostgreSQL, MySQL, MSSQL
- **Safe Execution**: SELECT-only queries with auto-correction and validation
- **Schema Understanding**: Automatically analyze database structure
- **Smart Joins**: Understand table relationships and create appropriate joins
- **Aggregations**: Support GROUP BY, COUNT, SUM, AVG, MAX, MIN, and complex analytics
- **Data Export**: Generate PDF reports from query results

{db_tools_text}

#### 3. Intelligent Query Routing (Advanced)
The unified agent system automatically:
- **SQL_ONLY**: Routes numeric/analytical questions to database
- **VECTOR_ONLY**: Routes policy/documentation questions to document search
- **HYBRID**: Combines database and document retrieval for complex queries
- **NO_RETRIEVAL**: Handles general conversation requiring no data access

#### 4. Self-Reflection & Quality Assurance
- **Response Evaluation**: Automatically assess response quality
- **Iterative Refinement**: Improve responses through feedback loops
- **Feedback Categories**:
  - SUFFICIENT: Response is complete and accurate
  - NEEDS_MORE_CONTEXT: Requires additional data
  - NEEDS_REFINEMENT: Quality can be improved
  - CONTRADICTORY: Contains conflicts requiring fixes

#### 5. RAG (Retrieval-Augmented Generation)
- **Semantic Search**: Find relevant documents by meaning, not keywords
- **Automatic Chunking**: Smart sentence-aware document splitting
- **Vector Embeddings**: ChromaDB integration for similarity search
- **Context Injection**: Relevant chunks automatically added to responses
- **Multi-Source**: Combine information from multiple documents

#### 6. Tool Integration & Execution
- **Multi-Step Chains**: Execute sequences of tools automatically
- **Smart Tool Selection**: Choose appropriate tools based on query
- **Error Handling**: Graceful fallbacks for missing tools
- **Custom Tools**: Support for user-defined function integration

### Guidelines for Optimal Performance

#### File Processing Rules
1. **When user references a file**: Automatically load it with `doc_loader`
2. **For Python files** (`.py`): Load with `doc_loader`, then use `code_reviewer` if needed
3. **For other files**: Use `doc_loader` only for inspection
4. **For databases**: Use appropriate database tools for analysis

#### Database Query Workflow (Critical!)
You MUST follow these rules for database questions:
1. If understanding database structure needed → Use `get_database_schema_info` first
2. For complex queries or uncertain structure → Use `get_table_preview` for sample data
3. Generate SQL based on user requests and execute directly with `execute_database_query`
4. **DO NOT** suggest queries to user before validating - always execute directly
5. `execute_database_query` automatically:
   - Validates and corrects table names (e.g., "customers" → "clients")
   - Validates and corrects column names (e.g., "client_id" → "customer_id")
   - Retries up to 10 times to fix invalid queries automatically
   - Returns results only when query is valid and successful
   - Returns error only if all correction attempts fail
6. All SQL must be single SELECT query (or PRAGMA). No INSERT/UPDATE/DELETE/DDL allowed
7. User should only see results or final errors - all correction happens automatically
8. Results may be exported to PDF after execution

#### RAG & Retrieval Guidelines
- Use ChromaDB collection to retrieve context when answering questions
- If referencing collection content, include matching chunks/summaries with citations
- Do NOT fabricate facts - explicitly state if knowledge base lacks information
- When using vault for context, label retrieved context as 'Relevant Context:'
- Avoid over-reliance on single short fragments

#### Response Guidelines
- **Conciseness**: Keep responses practical and focused
- **Formatting**: Use structured lists, code blocks for clarity
- **Actionability**: Provide direct, implementable recommendations
- **Completeness**: Always load and analyze relevant files before answering
- **Markdown**: Use full Markdown capabilities for readable, well-formatted responses
- **Context**: When using vault/database, clearly indicate source of information
- **Confidence**: Express uncertainty when data/context is incomplete

#### When to Use Which Tool

**For Code Analysis:**
- `doc_loader` → Examine file contents
- `code_reviewer` → Get detailed quality analysis

**For Database Questions:**
- `get_database_schema_info` → Understand structure
- `get_table_preview` → See sample data
- `execute_database_query` → Get results

**For Document Questions:**
- Vault retrieval → Find relevant context automatically
- `doc_loader` → Load specific documents if needed

**For Complex Queries:**
- Use routing decision (SQL vs Vector vs Hybrid)
- Combine results from multiple sources
- Present integrated answer with citations

### Your Strengths

✅ DevOps expertise and best practices
✅ Data analysis and SQL fluency
✅ Natural language understanding
✅ Document comprehension and synthesis
✅ Code quality evaluation
✅ Security-conscious design
✅ Error handling and recovery
✅ Integration thinking

### Your Limitations

⚠️ Cannot modify data (SELECT-only for safety)
⚠️ Cannot access external APIs beyond configured providers
⚠️ Cannot execute arbitrary code (tools are whitelisted)
⚠️ Cannot access files outside project directory
⚠️ Database access depends on configured permissions

### Error Handling Philosophy

- Graceful degradation when tools unavailable
- Informative error messages for debugging
- Automatic retry with corrections for queries
- Safe fallbacks for all critical operations
- Detailed logging for troubleshooting

### Remember

You are not just an LLM - you are a complete system that:
1. Understands queries intelligently (routing)
2. Retrieves relevant context (SQL + Vector)
3. Evaluates response quality (reflection)
4. Refines answers iteratively (self-reflection)
5. Executes tools safely (validation)
6. Provides comprehensive answers (integration)

Always act as this complete system, not just a language model. Leverage all capabilities available to provide the best possible answer.
"""


def _safe_bytes_len(value: Optional[str]) -> int:
    return len(value.encode('utf-8')) if value else 0


def _resolve_model_name(llm) -> Optional[str]:
    if llm is None:
        return None
    for attr in ('model', 'model_name', 'model_id', 'model_name_or_path'):
        name = getattr(llm, attr, None)
        if isinstance(name, str) and name:
            return name
    config = getattr(llm, 'config', None)
    if isinstance(config, dict):
        for key in ('model', 'model_name'):
            if config.get(key):
                return config[key]
    return None


def _extract_token_usage(ai_msg) -> Dict[str, Any]:
    token_usage: Dict[str, Any] = {}
    if ai_msg is None:
        return token_usage

    if hasattr(ai_msg, 'usage_metadata') and isinstance(ai_msg.usage_metadata, dict):
        token_usage.update(ai_msg.usage_metadata)

    response_meta = getattr(ai_msg, 'response_metadata', {}) or {}
    if isinstance(response_meta, dict):
        nested_usage = response_meta.get('token_usage')
        if isinstance(nested_usage, dict):
            token_usage.update(nested_usage)
        for key in ('input_tokens', 'output_tokens', 'total_tokens', 'prompt_tokens', 'completion_tokens'):
            if key in response_meta:
                token_usage[key] = response_meta[key]

    # Filter out non-numeric values to keep the log clean
    return {k: v for k, v in token_usage.items() if isinstance(v, (int, float))}


def install_package(package):
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', package])
        print(f"Successfully installed {package}")
    except subprocess.CalledProcessError:
        print(f"Failed to install {package}")
        sys.exit(1)


def get_api_key(provider):
    key = os.environ.get(f"{provider}_API_KEY")
    if not key:
        key = getpass.getpass(f"Enter API key for {provider}: ")
        with open('.env', 'a') as f:
            f.write(f"\n{provider}_API_KEY={key}")
    return key


def _log_import_error(package_name: str, error: Exception):
    """Log detailed import error with context."""
    print(f"\n🔴 ERROR: Could not import '{package_name}'", file=sys.stderr)
    print(f"   Python executable: {sys.executable}", file=sys.stderr)
    print(f"   Error: {error}", file=sys.stderr)
    print(f"\n🔧 Solution:", file=sys.stderr)
    print(f"   1. Make sure you're using the virtual environment:", file=sys.stderr)
    print(f"      $ source venv/bin/activate", file=sys.stderr)
    print(f"   2. Install the package:", file=sys.stderr)
    print(f"      $ pip install -r requirements.txt", file=sys.stderr)
    print()


def get_llm_provider(tools=None):
    # Get LLM provider from environment or user input
    llm_provider = os.getenv('LLM_PROVIDER', '').upper()
    valid_providers = ['OLLAMA', 'OPENAI', 'GOOGLE', 'ANTHROPIC']

    if llm_provider not in valid_providers:
        print('Please choose an LLM provider:')
        for i, provider in enumerate(valid_providers, 1):
            print(f"{i}. {provider}")
        try:
            choice = int(input('Enter your choice (1-4): ')) - 1
            if choice < 0 or choice >= len(valid_providers):
                raise ValueError('Invalid choice')
        except (ValueError, IndexError):
            print('Invalid choice. Using default provider.', file=sys.stderr)
            llm_provider = valid_providers[0]
        else:
            llm_provider = valid_providers[choice]
        with open('.env', 'a') as f:
            f.write(f"\nLLM_PROVIDER={llm_provider}")

    # Build default tools list
    if tools is None:
        tools = [doc_loader, code_reviewer]
        if DATABASE_TOOLS_AVAILABLE:
            tools.extend([
                get_database_schema_info,
                get_table_preview,
                validate_sql_query,
                execute_database_query,
            ])

    # Configure LLM based on provider
    if llm_provider == 'OLLAMA':
        try:
            from langchain_ollama import ChatOllama
        except ImportError as e:
            _log_import_error('langchain-ollama', e)
            raise

        model = os.getenv('OLLAMA_MODEL', 'llama2')

        # Check if model exists, if not pull it
        try:
            result = subprocess.run(['ollama', 'list'], capture_output=True, text=True, timeout=10)
            if model not in result.stdout:
                print(f"Model '{model}' not found locally. Pulling it now...")
                subprocess.run(['ollama', 'pull', model], check=True, timeout=300)
                print(f"Successfully pulled '{model}'")
        except subprocess.TimeoutExpired:
            print(f"Warning: Timeout checking/pulling Ollama model '{model}'")
        except FileNotFoundError:
            print('Warning: Ollama CLI not found. Make sure Ollama is installed and in PATH')
        except Exception as e:
            print(f"Warning: Could not verify/pull model: {str(e)}")

        llm = ChatOllama(model=model, temperature=0).bind_tools(tools)

    elif llm_provider == 'OPENAI':
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            install_package('langchain-openai')
            from langchain_openai import ChatOpenAI

        api_key = get_api_key('OPENAI')
        model = os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')
        llm = ChatOpenAI(api_key=api_key, model=model, temperature=0).bind_tools(tools)

    elif llm_provider == 'GOOGLE':
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError:
            install_package('langchain-google-genai')
            from langchain_google_genai import ChatGoogleGenerativeAI

        api_key = get_api_key('GOOGLE')
        model = os.getenv('GOOGLE_MODEL', 'gemini-pro')
        llm = ChatGoogleGenerativeAI(api_key=api_key, model=model, temperature=0).bind_tools(tools)

    elif llm_provider == 'ANTHROPIC':
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            install_package('langchain-anthropic')
            from langchain_anthropic import ChatAnthropic

        api_key = get_api_key('ANTHROPIC')
        model = os.getenv('ANTHROPIC_MODEL', 'claude-2')
        llm = ChatAnthropic(api_key=api_key, model=model, temperature=0).bind_tools(tools)
    return llm


def format_results_as_markdown(rows: list[dict], max_rows: int = 10) -> str:
    """Format a list of row dicts as a Markdown table.

    Returns a Markdown string (may include pipe characters). If rows is empty,
    returns a short message.
    """
    if not rows:
        return 'No results.'

    # Limit rows
    sample = rows[:max_rows]
    # Headers from the first row
    headers = list(sample[0].keys())
    # Build header row

    def esc(val: any) -> str:
        if val is None:
            return ''
        s = str(val)
        # escape pipe characters to avoid breaking table
        return s.replace('|', '\\|')

    header_row = '| ' + ' | '.join(headers) + ' |'
    sep_row = '| ' + ' | '.join(['---'] * len(headers)) + ' |'
    data_rows = []
    for r in sample:
        row_vals = [esc(r.get(h, '')) for h in headers]
        data_rows.append('| ' + ' | '.join(row_vals) + ' |')

    table = '\n'.join([header_row, sep_row] + data_rows)
    if len(rows) > max_rows:
        table += f"\n\n(Showing first {max_rows} of {len(rows)} rows)"
    return table
