#!/usr/bin/env python3
"""
Unified Interface - Single entry point for Chat, CLI, and Agentic RAG.

This module provides:
- Interactive Chat Mode: Conversational interface with tool execution
- CLI Mode: Command-line prompt execution  
- RAG Mode: Agentic RAG with self-reflection
- GUI Mode: Graphical interface (if available)

Usage:
  - Interactive Chat: python unified_interface.py
  - Direct Prompt: python unified_interface.py --prompt "your question"
  - Prompt File: python unified_interface.py --prompt-file path/to/prompt.txt
  - GUI Mode: python unified_interface.py --gui
  - Agentic RAG: python unified_interface.py --rag --query "your query"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

# Add current directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
llm_ci_dir = os.path.join(parent_dir, 'LLM_CI')

for path in [current_dir, parent_dir, llm_ci_dir]:
    if path not in sys.path:
        sys.path.insert(0, path)

# Configure logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class UnifiedInterface:
    """Unified interface combining Chat, CLI, RAG, and GUI modes."""
    
    def __init__(self):
        self.llm = None
        self.unified_agent = None
        self.chat_history = []
        self._init_llm()
        self._init_agent()
    
    def _init_llm(self):
        """Initialize LLM provider."""
        try:
            try:
                from Utils import get_llm_provider, system_message
                self.llm = get_llm_provider()
                self.system_message = system_message
                logger.info(f"✓ Initialized LLM provider from Utils")
            except (ImportError, AttributeError):
                # Fallback to direct initialization
                from langchain_ollama import OllamaLLM
                self.llm = OllamaLLM(
                    base_url=os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434'),
                    model=os.getenv('LLM_MODEL', 'gpt-oss:latest'),
                    temperature=0.3
                )
                self.system_message = "You are a helpful DevOps assistant."
                logger.info("✓ Initialized fallback OllamaLLM")
        except Exception as e:
            logger.error(f"✗ Failed to initialize LLM: {e}")
            sys.exit(1)
    
    def _init_agent(self):
        """Initialize Unified Agent."""
        try:
            from unified_agent import UnifiedAgent
            
            db_path = os.getenv('DB_PATH', 'sample_database.db')
            collection_name = os.getenv('CHROMA_COLLECTION', 'rag_collection')
            
            self.unified_agent = UnifiedAgent(
                base_url=os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434'),
                model=os.getenv('LLM_MODEL', 'gpt-oss:latest'),
                collection_name=collection_name,
                db_path=db_path,
                max_reflection_iterations=3
            )
            
            # Add database tools if available
            try:
                from database_tools import (
                    execute_database_query,
                    get_database_schema_info,
                    validate_sql_query
                )
                self.unified_agent.add_tool(
                    'execute_database_query',
                    execute_database_query,
                    'Execute SELECT or PRAGMA queries with automatic validation and correction'
                )
                self.unified_agent.add_tool(
                    'get_database_schema_info',
                    get_database_schema_info,
                    'Get the database schema including tables and columns'
                )
                self.unified_agent.add_tool(
                    'validate_sql_query',
                    validate_sql_query,
                    'Validate and auto-correct SQL queries before execution'
                )
                logger.info("✓ Loaded database tools from LLM_CI")
            except ImportError:
                logger.warning("⊘ Database tools not available, skipping")
            
            # Add document/vault tools if available
            try:
                from Tools import upload_file_to_vault
                self.unified_agent.add_tool(
                    'upload_file_to_vault',
                    upload_file_to_vault,
                    'Upload and index documents to the RAG vault'
                )
                logger.info("✓ Loaded document tools from Tools.py")
            except ImportError:
                logger.warning("⊘ Document tools not available, skipping")
            
            self.unified_agent.initialize_agent()
            logger.info("✓ Initialized UnifiedAgent with Agentic RAG")
        except Exception as e:
            logger.warning(f"⊘ Could not initialize UnifiedAgent: {e}")
            self.unified_agent = None
    
    def _preload_rag_documents(self):
        """Preload RAG documents from configured folder."""
        try:
            from Tools import load_folder_to_vault
            
            rag_dir = os.getenv('RAG_DOCS_DIR') or os.getenv('VAULT_DIR')
            if rag_dir and os.path.exists(rag_dir):
                logger.info(f"Preloading RAG documents from {rag_dir}")
                load_folder_to_vault(rag_dir, vault_path='vault.txt')
                
                # Compute and cache embeddings
                try:
                    from Utils import compute_and_cache_vault_embeddings
                    compute_and_cache_vault_embeddings(vault_path='vault.txt')
                    logger.info("✓ Cached RAG embeddings")
                except Exception:
                    logger.debug("Could not cache embeddings")
        except Exception as e:
            logger.warning(f"RAG preload failed: {e}")
    
    async def run_agentic_rag(self, query: str) -> Dict:
        """Run query through Agentic RAG pipeline."""
        if not self.unified_agent:
            return {
                'status': 'error',
                'error': 'UnifiedAgent not initialized',
                'result': None
            }
        
        logger.info(f"\n🔄 Processing query with Agentic RAG: {query}")
        result = await self.unified_agent.run(query)
        
        if result['status'] == 'success':
            logger.info(f"✓ RAG Pipeline Complete")
            logger.info(f"  Strategy: {result.get('routing_strategy', 'N/A')}")
            logger.info(f"  Result: {result.get('result', '')[:200]}...")
        else:
            logger.error(f"✗ RAG Pipeline Failed: {result.get('error')}")
        
        return result
    
    def run_cli_mode(self, prompt: str, verbose: bool = False):
        """Execute prompt in CLI mode."""
        try:
            from Utils import process_prompt
            
            logger.info(f"\n📝 Processing prompt in CLI mode")
            response = process_prompt(prompt, self.llm, verbose=verbose, usage_mode='cli')
            
            print("\n" + "="*60)
            print("RESPONSE:")
            print("="*60)
            print(response)
            print("="*60 + "\n")
            
            return response
        except Exception as e:
            logger.error(f"✗ CLI execution failed: {e}")
            print(f"Error: {e}")
            sys.exit(1)
    
    def run_chat_mode(self):
        """Run interactive chat mode."""
        try:
            from Utils import (
                create_tool_message,
                execute_tool,
                extract_tool_info,
                format_results_as_markdown,
                log_usage_entry,
                normalize_args,
                process_prompt,
                reset_chat_usage_log,
                system_message,
            )
            from database_tools import is_safe_select_query, validate_and_fix_sql, execute_query
            
            reset_chat_usage_log()
            chat_history = [('system', system_message)]
            pending_sql = None
            
            print("\n" + "="*60)
            print(f"💬 Chat Mode - Type 'exit' to quit")
            print(f"Commands: /execute, /cancel, /db <query>, /sql <query>")
            print("="*60 + "\n")
            
            while True:
                try:
                    question = input('You: ').strip()
                except (EOFError, KeyboardInterrupt):
                    logger.info('\nExiting chat...')
                    break
                
                if question.lower() in ['exit', 'quit']:
                    logger.info('Exiting chat...')
                    break
                
                if not question:
                    continue
                
                # Handle local commands
                cmd = question.strip().lower()
                
                if cmd in ['/execute', 'execute']:
                    if not pending_sql:
                        print("AI: No pending SQL to execute.\n")
                        continue
                    
                    pending_sql = pending_sql.rstrip(';')
                    ok, safety_msg = is_safe_select_query(pending_sql)
                    if not ok:
                        print(f"AI: Query blocked: {safety_msg}\n")
                        pending_sql = None
                        continue
                    
                    is_valid, msg, fixed_sql = validate_and_fix_sql(pending_sql)
                    if not is_valid:
                        print(f"AI: Cannot execute: {msg}\n")
                        pending_sql = None
                        continue
                    
                    rows, err = execute_query(fixed_sql)
                    if err:
                        print(f"AI: Error: {err}\n")
                    else:
                        print(f'\nAI: Query executed. Rows returned: {len(rows)}')
                        if rows:
                            table_md = format_results_as_markdown(rows, max_rows=10)
                            print('\n' + table_md + '\n')
                    pending_sql = None
                    continue
                
                if cmd in ['/cancel', 'cancel']:
                    if pending_sql:
                        pending_sql = None
                        print('AI: Pending SQL cancelled.\n')
                    else:
                        print('AI: Nothing to cancel.\n')
                    continue
                
                # Send to LLM
                chat_history.append(('human', question))
                tool_call_count = 0
                tool_error_count = 0
                
                while True:
                    try:
                        ai_msg = self.llm.invoke(chat_history)
                    except Exception as e:
                        logger.error(f"LLM invoke error: {e}")
                        print('AI: (Error occurred, please try again)\n')
                        break
                    
                    chat_history.append(ai_msg)
                    tool_calls = getattr(ai_msg, 'tool_calls', None) or []
                    
                    if not tool_calls:
                        response_text = getattr(ai_msg, 'content', '') or ''
                        if response_text:
                            try:
                                from Utils import convert_kv_text_to_markdown
                                conv = convert_kv_text_to_markdown(response_text)
                                print('\nAI:\n' + (conv if conv else response_text) + '\n')
                            except Exception:
                                print('\nAI:', response_text, '\n')
                            
                            # Check for SQL in response
                            try:
                                txt = response_text.strip()
                                if txt.upper().startswith('SELECT'):
                                    pending_sql = txt
                                    print("AI: SQL detected — type '/execute' to run, '/cancel' to discard.\n")
                            except Exception:
                                pass
                        break
                    
                    tool_call_count += len(tool_calls)
                    
                    # Execute tool calls
                    for tool_call in tool_calls:
                        try:
                            tool_name, tool_args, tool_id = extract_tool_info(tool_call)
                            tool_args = normalize_args(tool_args)
                            result = execute_tool(tool_name, tool_args)
                            chat_history.append(create_tool_message(result, tool_id))
                        except Exception as e:
                            tool_error_count += 1
                            chat_history.append(create_tool_message(f"Error: {e}", None))
        
        except Exception as e:
            logger.error(f"✗ Chat mode failed: {e}")
            print(f"Error: {e}")
            sys.exit(1)
    
    def run_gui_mode(self):
        """Run GUI mode if available."""
        try:
            from ChatGUI import run_gui
            logger.info("🖥️ Launching GUI...")
            run_gui()
        except ImportError:
            logger.error("✗ ChatGUI module not found. Install GUI dependencies and try again.")
            sys.exit(1)
        except Exception as e:
            logger.error(f"✗ GUI launch failed: {e}")
            sys.exit(1)
    
    def close(self):
        """Cleanup resources."""
        if self.unified_agent:
            self.unified_agent.close()


def main():
    parser = argparse.ArgumentParser(
        description='Unified Interface - Chat, CLI, RAG, and GUI modes',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python unified_interface.py                    # Interactive chat
  python unified_interface.py --prompt "question"
  python unified_interface.py --prompt-file prompt.txt
  python unified_interface.py --rag --query "your question"
  python unified_interface.py --gui              # Graphical mode
  python unified_interface.py --cli --verbose
        """
    )
    
    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--prompt',
        type=str,
        help='Direct prompt text (CLI mode)'
    )
    mode_group.add_argument(
        '--prompt-file',
        type=str,
        help='Path to prompt file (CLI mode)'
    )
    mode_group.add_argument(
        '--rag',
        action='store_true',
        help='Run Agentic RAG mode (requires --query)'
    )
    mode_group.add_argument(
        '--gui',
        action='store_true',
        help='Launch GUI mode'
    )
    
    parser.add_argument(
        '--query',
        type=str,
        help='Query for RAG mode'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output'
    )
    parser.add_argument(
        '--cli',
        action='store_true',
        help='Explicit CLI mode flag'
    )
    
    args = parser.parse_args()
    
    # Create interface
    interface = UnifiedInterface()
    
    try:
        # Preload RAG documents
        interface._preload_rag_documents()
        
        # Determine mode
        if args.gui:
            interface.run_gui_mode()
        
        elif args.rag:
            if not args.query:
                logger.error("--query required for RAG mode")
                sys.exit(1)
            result = asyncio.run(interface.run_agentic_rag(args.query))
            print("\n" + "="*60)
            print("RAG RESULT:")
            print("="*60)
            print(json.dumps(result, indent=2))
            print("="*60)
        
        elif args.prompt:
            interface.run_cli_mode(args.prompt, args.verbose)
        
        elif args.prompt_file:
            prompt_file = os.path.abspath(args.prompt_file)
            if not os.path.exists(prompt_file):
                logger.error(f"Prompt file not found: {prompt_file}")
                sys.exit(1)
            with open(prompt_file, 'r', encoding='utf-8') as f:
                prompt = f.read()
            interface.run_cli_mode(prompt, args.verbose)
        
        else:
            # Default: interactive chat
            interface.run_chat_mode()
    
    finally:
        interface.close()


if __name__ == '__main__':
    main()
