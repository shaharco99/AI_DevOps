from __future__ import annotations

import getpass
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from Tools import code_reviewer, doc_loader

try:
    from langchain_core.messages import ToolMessage
except ImportError:
    ToolMessage = None

# Load environment variables
load_dotenv()

# Usage logging configuration
_LOG_DIR = Path(os.getenv('LLM_USAGE_DIR', Path(__file__).resolve().parent / 'logs')).expanduser()
_LOG_DIR.mkdir(parents=True, exist_ok=True)
CLI_LOG_FILE = _LOG_DIR / 'cli_usage.jsonl'
CHAT_LOG_FILE = _LOG_DIR / 'chat_usage.jsonl'

# System message
system_message = (
    '=== Assistant Guidance ===\n\n'
    'You are a DevOps and CI/CD expert assistant. Provide concise, actionable technical guidance.\n\n'

    'Supported File Tools:\n'
    '- doc_loader: Read PDF, TXT, MD, CSV, JSON, HTML, DOCX, PPTX, XLSX files from current directory\n'
    '- code_reviewer: Analyze Python (.py) files for code quality (only specify file_name, no other parameters)\n\n'

    'Usage Instructions:\n'
    '1. When users reference files, automatically use the appropriate tool to load/review them\n'
    '2. For Python files (.py), use doc_loader and then if needed use code_reviewer with ONLY the file_name parameter (e.g., {"file_name": "ChatGUI.py"})\n'
    '3. For other files, use doc_loader to extract content\n'
    '4. For code_reviewer, do NOT pass line_number or scope - let it do a full review\n\n'

    'Response Guidelines:\n'
    '- Keep responses brief and focused on practical solutions\n'
    '- Use structured formatting (lists, code blocks) for clarity\n'
    '- Provide actionable recommendations\n'
    '- Always load and analyze relevant files before answering'
)


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
        'timestamp': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        'mode': mode,
        'provider': os.getenv('LLM_PROVIDER', '').upper(),
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

        llm = ChatOllama(model=model, temperature=0).bind_tools([doc_loader, code_reviewer] if tools is None else tools)

    elif llm_provider == 'OPENAI':
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            install_package('langchain-openai')
            from langchain_openai import ChatOpenAI

        api_key = get_api_key('OPENAI')
        model = os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')
        llm = ChatOpenAI(api_key=api_key, model=model, temperature=0).bind_tools([doc_loader, code_reviewer] if tools is None else tools)

    elif llm_provider == 'GOOGLE':
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError:
            install_package('langchain-google-genai')
            from langchain_google_genai import ChatGoogleGenerativeAI

        api_key = get_api_key('GOOGLE')
        model = os.getenv('GOOGLE_MODEL', 'gemini-pro')
        llm = ChatGoogleGenerativeAI(api_key=api_key, model=model, temperature=0).bind_tools([doc_loader, code_reviewer] if tools is None else tools)

    elif llm_provider == 'ANTHROPIC':
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            install_package('langchain-anthropic')
            from langchain_anthropic import ChatAnthropic

        api_key = get_api_key('ANTHROPIC')
        model = os.getenv('ANTHROPIC_MODEL', 'claude-2')
        llm = ChatAnthropic(api_key=api_key, model=model, temperature=0).bind_tools([doc_loader, code_reviewer] if tools is None else tools)
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
    return f"Unknown tool: {tool_name}"


def process_prompt(prompt, llm, verbose=False, output_stream=None, usage_mode: Optional[str] = None):
    """
    Process a single prompt and return the response.
    Handles tool calls automatically.

    Args:
        prompt: The prompt text to process
        llm: The LLM instance to use
        verbose: If True, print tool execution details
        output_stream: Stream to write verbose output to (default: sys.stderr)

    Returns:
        str: The final response from the LLM
    """
    import sys
    if output_stream is None:
        output_stream = sys.stderr

    chat_history = [('system', system_message), ('human', prompt)]
    tool_call_count = 0
    tool_error_count = 0
    last_ai_msg = None

    # Handle tool calls until final response
    try:
        while True:
            ai_msg = llm.invoke(chat_history)
            last_ai_msg = ai_msg
            chat_history.append(ai_msg)

            tool_calls = getattr(ai_msg, 'tool_calls', None) or []

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
                        print(f"tools in use: {tool_name} : parameters : {params_str}\n", file=output_stream)

                    # Execute tool
                    result = execute_tool(tool_name, tool_args)

                    if verbose:
                        print(f"Output:\n{result}\n", file=output_stream)

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
