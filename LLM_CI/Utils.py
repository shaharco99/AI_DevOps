from __future__ import annotations

import getpass
import hashlib as _hashlib
import json
import json as _json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as _np
from dotenv import load_dotenv

try:
    from Tools import code_reviewer, doc_loader
except Exception:
    code_reviewer = None
    doc_loader = None

try:
    from database_tools import execute_database_query, generate_and_preview_query, get_database_schema
    DATABASE_TOOLS_AVAILABLE = True
except ImportError:
    DATABASE_TOOLS_AVAILABLE = False
    generate_and_preview_query = None
    execute_database_query = None
    get_database_schema = None

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
    '- **generate_and_preview_query**: Used ONLY when you are uncertain how to construct a correct SELECT query based on the database schema.\n'
    '- **execute_database_query**: Execute SELECT queries directly after validating and auto-correcting them to fit the database schema.\n'
) if DATABASE_TOOLS_AVAILABLE else ''

system_message = f"""
## Assistant Guidance

You are a DevOps and CI/CD expert assistant. Provide concise, actionable technical guidance.

### Supported Tools
- **doc_loader**: Load PDF, TXT, MD, CSV, JSON, HTML, DOCX, PPTX, XLSX files from the current directory.
- **code_reviewer**: Analyze Python (.py) files for code quality.
{db_tools_text}

### RAG / Retrieval Guidelines
- Use the local vault (`VAULT_FILE`) to retrieve context when answering questions about documents or the repository.
- Prefer vector-based retrieval (cosine similarity) when embeddings are available; otherwise use word-overlap fallback.
- If you reference content from the vault, include the matching chunk(s) or summarize them and cite that they came from the local vault.
- Do not fabricate facts; if the vault or tools do not contain the information, be explicit about missing data.

### File Processing Rules
1. When a user references a file, automatically load it with **doc_loader**.
2. For `.py` files, first use **doc_loader**, then if needed call **code_reviewer** with ONLY the `file_name` parameter.
3. For all other file types, only use **doc_loader** to inspect content.

{('''### Database Query Workflow (Important!)
**You MUST follow these rules when handling database questions:**
1. If the user clearly requests simple data retrieval (e.g., 'show all users', 'get clients from USA'), call **execute_database_query** directly.
2. Use **generate_and_preview_query** ONLY when:
   - You are unsure of table or column names
   - Complex joins or relationships are required
   - Schema understanding is needed to build the correct query
3. All SQL must be a single SELECT query (or PRAGMA). No INSERT/UPDATE/DELETE/DDL allowed.
4. **execute_database_query** automatically validates the SQL:
   - Confirms tables exist
   - Confirms columns exist
   - Auto-corrects mismatched names when possible
   - Returns an error if the query cannot fit the database schema
5. Do NOT ask the user to approve queries unless they explicitly request preview.
6. Results may be exported to PDF after execution.
''') if DATABASE_TOOLS_AVAILABLE else ''}

### Response Guidelines
- Keep responses concise and practical.
- Use structured formatting (lists, code blocks) for clarity.
- Provide direct, actionable recommendations.
- Always load and analyze relevant files before answering.
- When using the vault for context, explicitly label retrieved context under 'Relevant Context:' and avoid over-reliance on a single short fragment.
- You have full Markdown capabilities—use them to make answers clear and readable.
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
    import torch as _torch
    TORCH_AVAILABLE = True
except Exception:
    TORCH_AVAILABLE = False

try:
    from Tools import VAULT_FILE
except Exception:
    VAULT_FILE = 'vault.txt'

# Module logger
logger = logging.getLogger(__name__)
_lvl = os.getenv('LOG_LEVEL', 'INFO').upper()
try:
    logger.setLevel(getattr(logging, _lvl))
except Exception:
    logger.setLevel(logging.INFO)


def get_relevant_context(rewritten_input: str, vault_embeddings=None, vault_content: Optional[list] = None, top_k: int = 3) -> list:
    """Return top-k relevant vault_content entries for rewritten_input.

    If `vault_embeddings` is provided and PyTorch is available, cosine
    similarity will be used. Otherwise a simple word-overlap heuristic is
    applied.
    """
    if not vault_content:
        logger.debug('get_relevant_context: empty vault_content')
        return []

    # Try vector search when embeddings are available or cached
    try:
        # If caller provided a torch tensor of embeddings
        if vault_embeddings is not None and TORCH_AVAILABLE and isinstance(vault_embeddings, _torch.Tensor):
            try:
                # compute query embedding if caller passed one as first element
                # otherwise fall back to overlap
                query_emb = None
                # Can't compute query embedding without a client here; skip
                if query_emb is not None:
                    cos_scores = _torch.cosine_similarity(query_emb.unsqueeze(0), vault_embeddings)
                    top_k = min(top_k, len(cos_scores))
                    top_indices = _torch.topk(cos_scores, k=top_k)[1].tolist()
                    return [vault_content[idx].strip() for idx in top_indices]
            except Exception:
                logger.debug('torch vector search failed', exc_info=True)
        # If caller provided numpy embeddings
        if vault_embeddings is not None and isinstance(vault_embeddings, (_np.ndarray, list, tuple)):
            try:
                emb_matrix = _np.array(vault_embeddings)
                # compute a simple bag-of-words embedding for the query as fallback
                q_vec = _simple_text_to_vector(rewritten_input, emb_matrix.shape[1])
                norms = _np.linalg.norm(emb_matrix, axis=1)
                qnorm = _np.linalg.norm(q_vec)
                if qnorm == 0 or norms.sum() == 0:
                    raise Exception('zero norm')
                scores = (emb_matrix @ q_vec) / (norms * qnorm + 1e-12)
                idxs = list(_np.argsort(scores)[::-1][:top_k])
                return [vault_content[i].strip() for i in idxs]
            except Exception:
                logger.debug('numpy vector search failed', exc_info=True)
        # Try loading cached embeddings from vault file and performing vector search
        cache_emb, cache_lines = _load_vault_embedding_cache()
        if cache_emb is not None and len(cache_lines) > 0:
            try:
                q_vec = _compute_query_vector(rewritten_input, cache_emb.shape[1])
                norms = _np.linalg.norm(cache_emb, axis=1)
                qnorm = _np.linalg.norm(q_vec)
                scores = (cache_emb @ q_vec) / (norms * qnorm + 1e-12)
                idxs = list(_np.argsort(scores)[::-1][:top_k])
                return [cache_lines[i].strip() for i in idxs]
            except Exception:
                logger.debug('cached vector search failed', exc_info=True)
    except Exception:
        logger.debug('vector search section failed', exc_info=True)
    # Simple word-overlap fallback scoring (if vector search didn't return)
    try:
        query_words = set(rewritten_input.lower().split())
        scores = []
        for i, txt in enumerate(vault_content):
            words = set(str(txt).lower().split())
            score = len(query_words.intersection(words))
            scores.append((score, i))
        scores.sort(key=lambda x: x[0], reverse=True)
        top = [vault_content[i].strip() for _, i in scores[:top_k] if scores]
        logger.debug('get_relevant_context returning %d items', len(top))
        return top
    except Exception:
        logger.exception('word-overlap fallback failed in get_relevant_context')
        return []


def _get_vault_path(vault_path: Optional[str] = None) -> str:
    return vault_path or VAULT_FILE or os.getenv('VAULT_FILE', 'vault.txt')


def _load_vault_lines(vault_path: Optional[str] = None) -> list:
    vp = _get_vault_path(vault_path)
    if not os.path.exists(vp):
        return []
    try:
        with open(vp, 'r', encoding='utf-8') as fh:
            return [ln.rstrip('\n') for ln in fh.readlines() if ln.strip()]
    except Exception:
        logger.exception('Failed to read vault file %s', vp)
        return []


def _cache_path_for_vault(vault_path: Optional[str] = None) -> str:
    vp = _get_vault_path(vault_path)
    return vp + '.emb.npz'


def _load_vault_embedding_cache(vault_path: Optional[str] = None) -> Tuple[Optional[_np.ndarray], list]:
    cp = _cache_path_for_vault(vault_path)
    if not os.path.exists(cp):
        return None, []
    try:
        data = _np.load(cp, allow_pickle=True)
        emb = data['embeddings']
        lines = data['lines'].tolist() if 'lines' in data else _load_vault_lines(vault_path)
        return emb, lines
    except Exception:
        logger.exception('Failed to load embedding cache %s', cp)
        return None, []


def _save_vault_embedding_cache(emb: _np.ndarray, lines: list, vault_path: Optional[str] = None) -> str:
    cp = _cache_path_for_vault(vault_path)
    try:
        _np.savez_compressed(cp, embeddings=emb, lines=_np.array(lines, dtype=object))
        return cp
    except Exception:
        logger.exception('Failed to save embedding cache %s', cp)
        return ''


def _simple_text_to_vector(text: str, dim: int) -> _np.ndarray:
    """Deterministic fallback vector for text: use SHA256 bytes to fill the vector."""
    if not text:
        return _np.zeros(dim, dtype=float)
    h = _hashlib.sha256(text.encode('utf-8')).digest()
    # Expand hash bytes to required dim by repeating and converting to floats
    b = bytearray(h)
    repeats = (dim + len(b) - 1) // len(b)
    arr = (b * repeats)[:dim]
    vec = _np.frombuffer(bytes(arr), dtype=_np.uint8).astype(float)
    # Normalize
    norm = _np.linalg.norm(vec)
    return vec / (norm + 1e-12)


def _compute_query_vector(query: str, dim: int) -> _np.ndarray:
    # Try Ollama/OpenAI if available; otherwise use simple fallback
    try:
        import ollama as _ollama  # type: ignore
        model = os.getenv('OLLAMA_EMBED_MODEL', 'mxbai-embed-large')
        resp = _ollama.embeddings(model=model, prompt=query)
        emb = _np.array(resp.get('embedding'))
        if emb.size == dim:
            return emb
        # else fall through to resizing
    except Exception:
        pass
    try:
        from openai import OpenAI as _OpenAI  # type: ignore
        client = _OpenAI()
        model = os.getenv('OPENAI_EMBED_MODEL', 'text-embedding-3-large')
        resp = client.embeddings.create(model=model, input=query)
        emb = _np.array(resp.data[0].embedding)
        if emb.size == dim:
            return emb
    except Exception:
        pass
    # fallback
    return _simple_text_to_vector(query, dim)


def compute_and_cache_vault_embeddings(vault_path: Optional[str] = None, dim: int = 384, force: bool = False) -> Tuple[Optional[_np.ndarray], list]:
    """Compute embeddings for every line in the vault and cache them.

    Attempts to use Ollama/OpenAI if available; otherwise uses a deterministic
    hash-based fallback so vector search can operate offline.
    """
    vp = _get_vault_path(vault_path)
    lines = _load_vault_lines(vp)
    if not lines:
        return None, []

    cp = _cache_path_for_vault(vp)
    if os.path.exists(cp) and not force:
        try:
            data = _np.load(cp, allow_pickle=True)
            return data['embeddings'], data['lines'].tolist()
        except Exception:
            logger.warning('Failed to read existing cache, will recompute', exc_info=True)

    emb_list = []
    # Try Ollama first
    try:
        import ollama as _ollama  # type: ignore
        model = os.getenv('OLLAMA_EMBED_MODEL', 'mxbai-embed-large')
        for ln in lines:
            resp = _ollama.embeddings(model=model, prompt=ln)
            emb_list.append(_np.array(resp.get('embedding')))
        emb = _np.vstack(emb_list)
        _save_vault_embedding_cache(emb, lines, vp)
        return emb, lines
    except Exception:
        logger.debug('Ollama embeddings not available or failed', exc_info=True)

    # Try OpenAI
    try:
        from openai import OpenAI as _OpenAI  # type: ignore
        client = _OpenAI()
        model = os.getenv('OPENAI_EMBED_MODEL', 'text-embedding-3-large')
        for ln in lines:
            resp = client.embeddings.create(model=model, input=ln)
            emb_list.append(_np.array(resp.data[0].embedding))
        emb = _np.vstack(emb_list)
        _save_vault_embedding_cache(emb, lines, vp)
        return emb, lines
    except Exception:
        logger.debug('OpenAI embeddings not available or failed', exc_info=True)

    # Fallback deterministic vectors
    for ln in lines:
        emb_list.append(_simple_text_to_vector(ln, dim))
    emb = _np.vstack(emb_list)
    _save_vault_embedding_cache(emb, lines, vp)
    return emb, lines


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


def ollama_chat(user_input: str, system_message: str, vault_embeddings, vault_content: list, ollama_model: Optional[str], conversation_history: list, client=None) -> str:
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

    relevant_context = get_relevant_context(rewritten_query, vault_embeddings, vault_content)
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
            tools.extend([generate_and_preview_query, execute_database_query, get_database_schema])

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
    elif tool_name == 'get_database_schema' and DATABASE_TOOLS_AVAILABLE:
        try:
            return get_database_schema.invoke(tool_args)
        except Exception as e:
            return f"Error executing get_database_schema: {e}"
    elif tool_name == 'generate_and_preview_query' and DATABASE_TOOLS_AVAILABLE:
        try:
            return generate_and_preview_query.invoke(tool_args)
        except Exception as e:
            return f"Error executing generate_and_preview_query: {e}"
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
