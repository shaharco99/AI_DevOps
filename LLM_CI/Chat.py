from __future__ import annotations

import logging
import os
import sys

from database_tools import (
    execute_query,
    is_safe_select_query,
    validate_and_fix_sql,
)
from Utils import (
    create_tool_message,
    execute_tool,
    extract_tool_info,
    format_results_as_markdown,
    get_llm_provider,
    log_usage_entry,
    normalize_args,
    process_prompt,
    reset_chat_usage_log,
    system_message,
)

LOG_LEVEL = os.getenv('LOG_LEVEL', 'ERROR').upper()
logging.basicConfig(level=logging.LOG_LEVEL)

# Initialize
llm_provider = os.getenv('LLM_PROVIDER', '')
# If user requested GUI, try launching it and exit the CLI
if '--gui' in sys.argv:
    try:
        from ChatGUI import run_gui
        run_gui()
        sys.exit(0)
    except Exception as e:
        logging.error(f"GUI start error: {e}")

try:
    llm = get_llm_provider()
except Exception as e:
    logging.error(f"Error initializing LLM: {e}",)
    sys.exit(1)

# Preload RAG documents from configured folder (if any)
try:
    from Tools import load_folder_to_vault
    rag_dir = os.getenv('RAG_DOCS_DIR') or os.getenv('VAULT_DIR')
    if rag_dir:
        logging.info(f"Preloading RAG documents from {rag_dir}")
        try:
            load_folder_to_vault(rag_dir, vault_path='vault.txt')
            # Compute and cache embeddings for vector retrieval by default
            try:
                from Utils import compute_and_cache_vault_embeddings
                compute_and_cache_vault_embeddings(vault_path='vault.txt')
            except Exception:
                logging.debug('Could not compute embeddings at startup; continuing without cache')
        except Exception as e:
            logging.warning(f"RAG preload failed: {e}")
except Exception:
    logging.debug('No Tools.load_folder_to_vault available')

logging.info(f"DevOps Chat with {llm_provider}! Type 'exit' to quit.\n")

reset_chat_usage_log()

chat_history = [('system', system_message)]

# Main chat loop
pending_sql = None
while True:
    try:
        question = input('You: ')
    except (EOFError, KeyboardInterrupt):
        logging.info('\nExiting chat...')
        break

    if question.lower() in ['exit', 'quit']:
        logging.info('Exiting chat...')
        break

    # Handle approval/cancel commands locally before sending to LLM
    cmd = question.strip().lower()
    if cmd in ['/execute', 'execute', '/excute', 'excute', '/run', 'run']:
        if not pending_sql:
            print("AI: No pending SQL to execute. Generate a query first with '/db' or '/sql'.\n")
            continue

        # Normalize SQL (strip trailing semicolon) and validate safety
        pending_sql = pending_sql.rstrip().rstrip(';')
        ok, safety_msg = is_safe_select_query(pending_sql)
        if not ok:
            print(f"AI: Query blocked: {safety_msg}\n")
            pending_sql = None
            continue

        is_valid, msg, fixed_sql = validate_and_fix_sql(pending_sql)
        if not is_valid:
            print(f"AI: Cannot execute query: {msg}\n")
            pending_sql = None
            continue

        rows, err = execute_query(fixed_sql)
        if err:
            print(f"AI: Execution error: {err}\n")
        else:
            # Show concise result: up to 10 rows in Markdown table format
            print('\nAI: Query executed successfully. Rows returned:', len(rows))
            if rows:
                # If multiple rows, render as a Markdown table for clearer tabular layout
                if len(rows) > 1:
                    table_md = format_results_as_markdown(rows, max_rows=10)
                    print('\n' + table_md + '\n')
                else:
                    # Single-row: print concise key: value lines for readability
                    single = rows[0]
                    if isinstance(single, dict):
                        lines = '\n'.join(f"{k}: {v}" for k, v in single.items())
                        print('\n' + lines + '\n')
                    else:
                        print('\n' + str(single) + '\n')
        pending_sql = None
        continue

    if cmd in ['/cancel', 'cancel']:
        if pending_sql:
            pending_sql = None
            print('AI: Pending SQL cancelled.\n')
        else:
            print('AI: Nothing to cancel.\n')
        continue

    chat_history.append(('human', question))

    # Loop until final response (allows multi-step tool execution chains)
    tool_call_count = 0
    tool_error_count = 0
    while True:
        try:
            # If the user asked for DB help using a simple command prefix, run the RAG flow.
            if isinstance(question, str) and (question.startswith('/db ') or question.startswith('/sql ')):
                user_q = question.split(' ', 1)[1].strip()

                def llm_callable(prompt_text: str) -> str:
                    try:
                        resp = process_prompt(prompt_text, llm, verbose=False, conversation_history=chat_history)
                        if isinstance(resp, tuple):
                            return resp[0]
                        return resp
                    except Exception:
                        return ''

                # Database queries are now handled through tools - let the LLM generate SQL using tools
                # The LLM will use get_database_schema_info and validate_sql_query tools
                ai_msg = llm.invoke(chat_history)
            else:
                ai_msg = llm.invoke(chat_history)
        except Exception as e:
            log_usage_entry(
                mode='chat',
                prompt=question,
                response='',
                ai_msg=None,
                tool_calls=tool_call_count,
                llm=llm,
                extra={
                    'conversation_turns': len(chat_history),
                    'tool_errors': tool_error_count,
                    'error': f"invoke_error: {e}",
                },
            )
            logging.error(f"Error invoking LLM: {e}")
            logging.error('AI: (Error occurred, please try again)\n')
            break

        chat_history.append(ai_msg)

        tool_calls = getattr(ai_msg, 'tool_calls', None) or []

        # If final response (no tool calls), show friendly output and stop
        if not tool_calls:
            response_text = getattr(ai_msg, 'content', '') or ''
            if response_text:
                # If assistant produced repeated Key: value blocks, convert to a Markdown table for CLI
                try:
                    from Utils import convert_kv_text_to_markdown
                    conv = convert_kv_text_to_markdown(response_text)
                    if conv:
                        print('\nAI:\n' + conv + '\n')
                    else:
                        print('\nAI:', response_text, '\n')
                except Exception:
                    print('\nAI:', response_text, '\n')
                # If the assistant returned a SQL query directly, mark it as pending for approval
                try:
                    txt = response_text.strip()
                    if txt.upper().startswith('SELECT'):
                        pending_sql = txt
                        print("AI: Detected SQL in assistant response — type '/execute' to run it, or '/cancel' to discard.\n")
                except Exception:
                    pass
            log_usage_entry(
                mode='chat',
                prompt=question,
                response=response_text,
                ai_msg=ai_msg,
                tool_calls=tool_call_count,
                llm=llm,
                extra={
                    'conversation_turns': len(chat_history),
                    'tool_errors': tool_error_count,
                },
            )
            break

        tool_call_count += len(tool_calls)

        # Execute tool calls silently and add results to history for LLM
        for tool_call in tool_calls:
            try:
                tool_name, tool_args, tool_id = extract_tool_info(tool_call)
                tool_args = normalize_args(tool_args)

                result = execute_tool(tool_name, tool_args)
                chat_history.append(create_tool_message(result, tool_id))
            except Exception as e:
                tool_error_count += 1
                error_msg = f"Error parsing tool call: {e}"
                chat_history.append(create_tool_message(error_msg, None))
