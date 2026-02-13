from __future__ import annotations

import getpass
import json
import json as _json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

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

try:
    from langchain_core.messages import ToolMessage
except ImportError:
    ToolMessage = None

# Load environment variables
load_dotenv()

# Logging: write to repository-root `logs/` by default, but allow overrides.
# Filenames include a timestamp by default to avoid daily overwrite; set
# `LOG_USE_TIMESTAMP=false` to use date-only filenames. CI environments can
# override the directory using `LOG_DIR_OVERRIDE`.
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_DIR = REPO_ROOT / 'logs'
LOG_DIR_OVERRIDE = os.getenv('LOG_DIR_OVERRIDE')
_BASE_LOG_DIR = Path(LOG_DIR_OVERRIDE) if LOG_DIR_OVERRIDE else DEFAULT_LOG_DIR
_BASE_LOG_DIR.mkdir(parents=True, exist_ok=True)
# include timestamp in filenames by default to avoid overwriting logs
LOG_USE_TIMESTAMP = os.getenv('LOG_USE_TIMESTAMP', 'true').lower() in ('1', 'true', 'yes')
_now = datetime.now(timezone.utc)
if LOG_USE_TIMESTAMP:
    _TS = _now.strftime('%Y-%m-%d_%H%M%S')
else:
    _TS = _now.strftime('%Y-%m-%d')
CLI_LOG_FILE = _BASE_LOG_DIR / f"{_TS}_cli.jsonl"
CHAT_LOG_FILE = _BASE_LOG_DIR / f"{_TS}_chat.jsonl"

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


def reset_chat_usage_log():
    """
    Reset the chat usage log at the beginning of every interactive chat session.
    """
    CHAT_LOG_FILE.write_text('', encoding='utf-8')


def _append_usage_entry(log_file: Path, entry: Dict[str, Any]):
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(entry, ensure_ascii=True) + '\n')


# ---------------------------------------------------------------------
# Simple RAG / rewrite helpers (merged from localrag.py)
# These provide basic functionality when no external LLM/embedding clients
# are available; when clients are passed in they will be used.
# ---------------------------------------------------------------------


try:
    import chromadb
    from Tools import CHROMA_COLLECTION
except Exception:
    chromadb = None
    CHROMA_COLLECTION = 'rag_collection'

# Module logger
logger = logging.getLogger(__name__)
_lvl = os.getenv('LOG_LEVEL', 'INFO').upper()
try:
    logger.setLevel(getattr(logging, _lvl))
except Exception:
    logger.setLevel(logging.INFO)


def get_relevant_context(rewritten_input: str, collection_name: str = 'rag_collection', top_k: int = 3) -> list:
    """Return top-k relevant entries from a ChromaDB collection.
    """
    if not chromadb:
        return []

    try:
        client = chromadb.Client()
        collection = client.get_collection(name=collection_name or CHROMA_COLLECTION)
        results = collection.query(
            query_texts=[rewritten_input],
            n_results=top_k
        )
        return results.get('documents', [])[0]
    except Exception:
        logger.exception("Error querying ChromaDB collection '%s'", collection_name)
        return []


def rewrite_query(user_input_json: str, conversation_history: list, client=None, ollama_model: Optional[str] = None) -> str:
    """Rewrite the query JSON into a clarified query string JSON output.

    This function mirrors the original behavior but does not require an LLM.
    If `client` is provided it will be used (best-effort). Otherwise the
    original query is returned as the rewritten query.
    """
    try:
        data = _json.loads(user_input_json)
        user_input = data.get('Query', '')
    except Exception:
        user_input = user_input_json
    logger.debug('rewrite_query received: %s', user_input)

    # Build a small context from last two messages
    context = '\n'.join([f"{msg.get('role')}: {msg.get('content')}" for msg in (conversation_history or [])[-2:]])

    # If an LLM client is supplied, attempt to use it
    if client is not None:
        try:
            prompt = f"Rewrite the query using the conversation context. Context:\n{context}\nOriginal: [{user_input}]\nRewritten query:"
            resp = client.chat.completions.create(
                model=ollama_model or 'llama3',
                messages=[{'role': 'system', 'content': prompt}],
                max_tokens=200,
                n=1,
                temperature=0.1,
            )
            rewritten_query = getattr(resp.choices[0].message, 'content', str(resp)).strip()
            logger.debug('rewrite_query got LLM response')
            return _json.dumps({'Rewritten Query': rewritten_query})
        except Exception:
            logger.warning('rewrite_query: LLM client call failed, falling back', exc_info=True)

    # Fallback: return original query unchanged in the same JSON wrapper
    logger.debug('rewrite_query fallback returning original query')
    return _json.dumps({'Rewritten Query': user_input})


def ollama_chat(user_input: str, system_message: str, ollama_model: Optional[str], conversation_history: list, client=None) -> str:
    """Simple chat wrapper to integrate rewritten queries and context.

    If `client` is provided a real LLM call will be attempted; otherwise a
    deterministic echoed response is returned so GUI/CLI code can use this
    without an external service during tests.
    """
    logger.debug('ollama_chat called with user_input: %s', user_input)
    conversation_history.append({'role': 'user', 'content': user_input})

    if len(conversation_history) > 1:
        query_json = {'Query': user_input, 'Rewritten Query': ''}
        rewritten_query_json = rewrite_query(_json.dumps(query_json), conversation_history, client=client, ollama_model=ollama_model)
        rewritten_query_data = _json.loads(rewritten_query_json)
        rewritten_query = rewritten_query_data.get('Rewritten Query', user_input)
    else:
        rewritten_query = user_input

    relevant_context = get_relevant_context(rewritten_query)
    context_str = '\n'.join(relevant_context) if relevant_context else ''

    user_input_with_context = user_input
    if relevant_context:
        user_input_with_context = user_input + '\n\nRelevant Context:\n' + context_str

    conversation_history[-1]['content'] = user_input_with_context

    # If a client is provided, attempt a real completion
    if client is not None:
        try:
            messages = [{'role': 'system', 'content': system_message}, *conversation_history]
            resp = client.chat.completions.create(model=ollama_model or 'llama3', messages=messages, max_tokens=2000)
            content = getattr(resp.choices[0].message, 'content', str(resp))
            conversation_history.append({'role': 'assistant', 'content': content})
            logger.debug('ollama_chat received response from client')
            return content
        except Exception:
            logger.warning('ollama_chat client call failed, using fallback echo', exc_info=True)

    # Fallback deterministic reply for offline usage / tests
    reply = 'Echo: ' + user_input_with_context
    conversation_history.append({'role': 'assistant', 'content': reply})
    logger.debug('ollama_chat returning fallback echo reply')
    return reply


def log_usage_entry(
    *,
    mode: str,
    prompt: Optional[str],
    response: Optional[str],
    ai_msg: Any,
    tool_calls: int,
    llm: Any,
    extra: Optional[Dict[str, Any]] = None,
):
    """
    Persist usage metrics for CLI and Chat interactions.
    """
    log_file = CHAT_LOG_FILE if mode == 'chat' else CLI_LOG_FILE
    entry: Dict[str, Any] = {
        # timezone-aware ISO timestamp
        'timestamp': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'mode': mode,
        'provider': os.getenv('LLM_PROVIDER', ''),
        'model': _resolve_model_name(llm),
        'prompt_chars': len(prompt) if prompt else 0,
        'prompt_bytes': _safe_bytes_len(prompt),
        'response_chars': len(response) if response else 0,
        'response_bytes': _safe_bytes_len(response),
        'tool_calls': tool_calls,
    }
    token_usage = _extract_token_usage(ai_msg)
    if token_usage:
        entry['token_usage'] = token_usage
    if extra:
        entry.update(extra)
    _append_usage_entry(log_file, entry)


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
        from langchain_ollama import ChatOllama

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


def extract_tool_info(tool_call):
    """Extract tool name, args, and ID from a tool call object or dict."""
    if hasattr(tool_call, 'name'):
        return tool_call.name, getattr(tool_call, 'args', {}), getattr(tool_call, 'id', None)
    elif isinstance(tool_call, dict):
        name = tool_call.get('name') or tool_call.get('tool')
        args = tool_call.get('args') or tool_call.get('arguments', {})
        tool_id = tool_call.get('id') or tool_call.get('tool_call_id')
        return name, args, tool_id
    else:
        name = getattr(tool_call, 'name', None) or getattr(tool_call, 'tool', 'unknown')
        args = getattr(tool_call, 'args', {}) or getattr(tool_call, 'arguments', {})
        tool_id = getattr(tool_call, 'id', None) or getattr(tool_call, 'tool_call_id', None)
        return name, args, tool_id


def normalize_args(args):
    """Convert args to dict format, handling JSON strings."""
    if isinstance(args, str):
        try:
            return json.loads(args)
        except json.JSONDecodeError:
            return {}
    return args if isinstance(args, dict) else {}


def create_tool_message(content, tool_id):
    """Create a ToolMessage object or tuple based on availability."""
    if ToolMessage and tool_id:
        return ToolMessage(content=str(content), tool_call_id=tool_id)
    return ('tool', str(content))


def execute_tool(tool_name, tool_args):
    """Execute a tool and return the result."""
    if tool_name == 'doc_loader':
        try:
            return doc_loader.invoke(tool_args)
        except Exception as e:
            return f"Error executing doc_loader: {e}"
    elif tool_name == 'code_reviewer':
        try:
            return code_reviewer.invoke(tool_args)
        except Exception as e:
            return f"Error executing code_reviewer: {e}"
    elif tool_name == 'get_database_schema_info' and DATABASE_TOOLS_AVAILABLE:
        try:
            return get_database_schema_info.invoke(tool_args)
        except Exception as e:
            return f"Error executing get_database_schema_info: {e}"
    elif tool_name == 'get_table_preview' and DATABASE_TOOLS_AVAILABLE:
        try:
            return get_table_preview.invoke(tool_args)
        except Exception as e:
            return f"Error executing get_table_preview: {e}"
    elif tool_name == 'validate_sql_query' and DATABASE_TOOLS_AVAILABLE:
        try:
            return validate_sql_query.invoke(tool_args)
        except Exception as e:
            return f"Error executing validate_sql_query: {e}"
    elif tool_name == 'execute_database_query' and DATABASE_TOOLS_AVAILABLE:
        try:
            return execute_database_query.invoke(tool_args)
        except Exception as e:
            return f"Error executing execute_database_query: {e}"
    return f"Unknown tool: {tool_name}"


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


def convert_kv_text_to_markdown(text: str) -> str | None:
    """Detect repeated 'Key: value' sequences in free text and convert to a Markdown table.

    Returns a Markdown table string if conversion is possible, otherwise None.
    This is intentionally conservative: it only converts when it detects multiple records
    formed by repeated occurrences of the same 'first key' (e.g., 'Order ID').
    """
    if not text:
        return None

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # Extract candidate key:value lines (strip leading enumerators like '1.')
    kv_lines = []
    title = None
    for ln in lines:
        # Remove numeric enumerators like '1.' or '1)'
        ln_clean = ln
        m = __import__('re').match(r'^\s*\d+[\.)]?\s*(.*)$', ln)
        if m:
            ln_clean = m.group(1)
        if ':' in ln_clean:
            k, v = ln_clean.split(':', 1)
            k = k.strip()
            v = v.strip()
            # If this is a colon-terminated line with no value, treat it as a title
            if v == '' and len(k.split()) > 2 and title is None:
                title = k.rstrip(':')
                continue
            kv_lines.append((k, v))

    if not kv_lines:
        return None

    # Determine first key and partition into records when the first key repeats
    first_key = kv_lines[0][0]
    records = []
    cur = {}
    for k, v in kv_lines:
        if k == first_key and cur:
            records.append(cur)
            cur = {}
        cur[k] = v
    if cur:
        records.append(cur)

    # Allow conversion for a single record as well (render a one-row table)
    if len(records) < 1:
        return None

    # Normalize headers order based on first record keys, then any additional keys
    headers = []
    for r in records:
        for k in r.keys():
            if k not in headers:
                headers.append(k)

    # Build rows as dicts with consistent headers
    rows = []
    for r in records:
        row = {h: r.get(h, '') for h in headers}
        rows.append(row)

    md = format_results_as_markdown(rows, max_rows=len(rows))
    if title:
        return f"**{title}**\n\n" + md
    return md


def convert_kv_text_to_html(text: str) -> str | None:
    """Convert repeated Key: value blocks into an HTML table for GUI rendering.

    Returns an HTML string containing a styled table, or None if conversion not applicable.
    """
    if not text:
        return None

    raw_lines = text.splitlines()
    records = []
    cur = {}
    first_key = None
    title = None

    for ln in raw_lines:
        ln_stripped = ln.strip()
        if ln_stripped == '':
            # blank line denotes end of current record
            if cur:
                records.append(cur)
                cur = {}
            continue

        # Remove enumerator like '1.' or '1)'
        m = __import__('re').match(r'^\s*\d+[\.)]?\s*(.*)$', ln_stripped)
        content = m.group(1) if m else ln_stripped

        if ':' in content:
            k, v = content.split(':', 1)
            key = k.strip()
            val = v.strip()
            # Treat a colon-terminated line with no value as a title (e.g. 'The completed orders from 2023 are:')
            if val == '' and len(key.split()) > 2 and title is None:
                title = key.rstrip(':')
                continue
            if first_key is None:
                first_key = key
            # If we see the first key again and cur has content, start a new record
            if first_key and key == first_key and cur:
                records.append(cur)
                cur = {}
            cur[key] = val
        else:
            # not a key:value line; skip
            continue

    if cur:
        records.append(cur)

    # Allow conversion for a single record as well (render a one-row table)
    if len(records) < 1:
        return None

    # Build ordered headers
    headers = []
    for r in records:
        for k in r.keys():
            if k not in headers:
                headers.append(k)

    # Build HTML table
    def esc(s: str) -> str:
        import html
        return html.escape(str(s))

    thead = ''.join(f'<th style="text-align:left;padding:8px 12px;border-bottom:2px solid #e6e6e6">{esc(h)}</th>' for h in headers)
    rows_html = ''
    for r in records:
        tds = ''.join(f'<td style="padding:8px 12px;border-bottom:1px solid #f0f0f0">{esc(r.get(h, ""))}</td>' for h in headers)
        rows_html += f'<tr>{tds}</tr>'

    # Add some bottom padding so last row isn't visually clipped in the bubble
    table_html = (
        '<div style="overflow:auto;max-width:100%;margin-top:6px;padding-bottom:8px">'
        '<table style="border-collapse:collapse;width:100%;font-family:Segoe UI,Arial,Helvetica,sans-serif;">'
        f'<thead><tr>{thead}</tr></thead><tbody>{rows_html}</tbody></table></div>'
    )

    if title:
        title_html = f'<div style="font-weight:700;margin-bottom:8px">{esc(title)}</div>'
        return title_html + table_html
    return table_html


def process_prompt(prompt, llm, verbose=False, output_stream=None, usage_mode: Optional[str] = None, conversation_history: Optional[list] = None):
    """
    Process a single prompt and return the response.
    Handles tool calls automatically and maintains conversation history.

    Args:
        prompt: The prompt text to process
        llm: The LLM instance to use
        verbose: If True, print tool execution details
        output_stream: Stream to write verbose output to (default: sys.stderr)
        usage_mode: 'cli' or 'chat' for usage logging
        conversation_history: Optional list of previous messages to maintain context

    Returns:
        tuple: (response_text, updated_chat_history) - The final response and full conversation history
    """
    import sys
    if output_stream is None:
        output_stream = sys.stderr

    # Initialize chat history: use provided history if given (even empty list), otherwise start fresh
    if conversation_history is not None:
        chat_history = list(conversation_history)
        # Ensure system message exists at start
        if not chat_history or not (isinstance(chat_history[0], tuple) and chat_history[0][0] == 'system'):
            chat_history.insert(0, ('system', system_message))
    else:
        chat_history = [('system', system_message)]

    # Add the new user prompt
    chat_history.append(('human', prompt))

    tool_call_count = 0
    tool_error_count = 0
    last_ai_msg = None

    # Handle tool calls until final response
    try:
        if verbose:
            logging.debug(f"Starting process_prompt; initial chat_history length={len(chat_history)}")
            for i, item in enumerate(chat_history[:5]):
                t = type(item)
                preview = ''
                try:
                    if isinstance(item, tuple):
                        preview = str(item[1])[:120]
                    else:
                        preview = getattr(item, 'content', str(item))[:120]
                except Exception:
                    preview = str(item)
                print(f"  [{i}] {t} -> {preview}")

        while True:
            ai_msg = llm.invoke(chat_history)
            last_ai_msg = ai_msg
            chat_history.append(ai_msg)

            tool_calls = getattr(ai_msg, 'tool_calls', None) or []

            # Debug: Log what we got from the LLM
            if verbose:
                logging.debug(f"ai_msg type: {type(ai_msg)}")
                logging.debug(f"ai_msg.content: {ai_msg.content[:200] if hasattr(ai_msg, 'content') else 'N/A'}")
                logging.debug(f"tool_calls count: {len(tool_calls)}")
                if tool_calls:
                    logging.debug(f"tool_calls: {tool_calls}")

            if not tool_calls:
                # Final response
                final_response = ai_msg.content if ai_msg.content else '(no response)'
                if usage_mode:
                    log_usage_entry(
                        mode=usage_mode,
                        prompt=prompt,
                        response=final_response,
                        ai_msg=ai_msg,
                        tool_calls=tool_call_count,
                        llm=llm,
                        extra={
                            'conversation_turns': len(chat_history),
                            'tool_errors': tool_error_count,
                        },
                    )
                # Return both the response and updated history for GUI when a conversation_history was provided
                if conversation_history is not None:
                    if verbose:
                        logging.debug(f"Returning response and chat_history (len={len(chat_history)})")
                    return final_response, chat_history
                return final_response

            tool_call_count += len(tool_calls)

            # Execute tool calls
            for tool_call in tool_calls:
                try:
                    tool_name, tool_args, tool_id = extract_tool_info(tool_call)
                    tool_args = normalize_args(tool_args)

                    if verbose:
                        # Print tool usage
                        params_str = json.dumps(tool_args) if tool_args else '{}'
                        print(f"tools in use: {tool_name} : parameters : {params_str}\n")

                    # Execute tool
                    result = execute_tool(tool_name, tool_args)

                    if verbose:
                        print(f"Output:\n{result}\n")

                    # Add result to history
                    chat_history.append(create_tool_message(result, tool_id))
                except Exception as e:
                    tool_error_count += 1
                    error_msg = f"Error parsing tool call: {e}"
                    chat_history.append(create_tool_message(error_msg, None))
    except Exception as exc:
        if usage_mode:
            log_usage_entry(
                mode=usage_mode,
                prompt=prompt,
                response='',
                ai_msg=last_ai_msg,
                tool_calls=tool_call_count,
                llm=llm,
                extra={
                    'conversation_turns': len(chat_history),
                    'tool_errors': tool_error_count,
                    'error': str(exc),
                },
            )
        raise
