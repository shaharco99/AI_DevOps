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
from typing import Dict, Optional

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
        self._runner = None
        self._init_llm()
        self._init_agent()
        # Create a persistent async runner to avoid repeated loop creation
        try:
            self._runner = AsyncRunner()
        except Exception:
            self._runner = None
    
    def _init_llm(self):
        """Initialize LLM provider."""
        try:
            try:
                from Utils import get_llm_provider, system_message
                self.llm = get_llm_provider()
                self.system_message = system_message
                logger.info(f"✓ Initialized LLM provider from Utils")
            except (ImportError, AttributeError) as e:
                # Fallback to direct initialization
                from langchain_ollama import OllamaLLM
                self.llm = OllamaLLM(
                    base_url=os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434'),
                    model=os.getenv('LLM_MODEL', 'gpt-oss:latest'),
                    temperature=0.3
                )
                self.system_message = "You are a helpful DevOps assistant."
                logger.info("✓ Initialized fallback OllamaLLM")
        except ImportError as e:
            logger.error(f"✗ Failed to initialize LLM: {e}")
            logger.error(f"  Python executable: {sys.executable}")
            logger.error(f"  Missing package: {str(e).split()[-1] if str(e) else 'unknown'}")
            logger.error(f"\n  To fix:")
            logger.error(f"  1. Activate virtual environment: source venv/bin/activate")
            logger.error(f"  2. Install requirements: pip install -r requirements.txt")
            sys.exit(1)
        except Exception as e:
            logger.error(f"✗ Unexpected error during LLM initialization: {e}")
            logger.error(f"  Python executable: {sys.executable}")
            sys.exit(1)
    
    def _init_agent(self):
        """Initialize Unified Agent."""
        try:
            from unified_agent import UnifiedAgent
            
            db_path = os.getenv('DB_PATH', 'sample_database.db')
            collection_name = os.getenv('CHROMA_COLLECTION', 'rag_collection')
            
            # Initialize the agent
            try:
                self.unified_agent = UnifiedAgent(
                    base_url=os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434'),
                    model=os.getenv('LLM_MODEL', 'gpt-oss:latest'),
                    collection_name=collection_name,
                    db_path=db_path,
                    max_reflection_iterations=3
                )
            except Exception as e:
                logger.error(f"Failed to create UnifiedAgent: {e}")
                raise
            
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
            except ImportError as e:
                logger.warning(f"⊘ Database tools not available: {e}")
            except Exception as e:
                logger.error(f"Error adding database tools: {e}")
            
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
                logger.debug("⊘ Document tools not available")
            except Exception as e:
                logger.error(f"Error adding document tools: {e}")
            
            # Initialize the agent
            try:
                self.unified_agent.initialize_agent()
                logger.info("✓ Initialized UnifiedAgent with Agentic RAG")
            except Exception as e:
                logger.error(f"Failed to initialize agent: {e}")
                raise
                
        except Exception as e:
            logger.error(f"✗ Could not initialize UnifiedAgent: {e}", exc_info=True)
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
        """Execute prompt in CLI mode using the UnifiedAgent."""
        if not self.unified_agent:
            logger.error("✗ UnifiedAgent not initialized. Cannot start CLI mode.")
            sys.exit(1)

        logger.info(f"\n📝 Processing prompt in CLI mode with UnifiedAgent")

        # Run the agent with the user's query using the persistent runner
        if self._runner:
            result = self._runner.run(self.run_agentic_rag(prompt))
        else:
            result = asyncio.run(self.run_agentic_rag(prompt))

        # Display the result
        if result['status'] == 'success':
            response = result.get('result', 'No result returned.')
            print("\n" + "="*60)
            print("RESPONSE:")
            print("="*60)
            print(response)
            print("="*60 + "\n")
            return response
        else:
            error_message = result.get('error', 'An unknown error occurred.')
            print("\n" + "="*60)
            print("ERROR:")
            print("="*60)
            print(error_message)
            print("="*60 + "\n")
            sys.exit(1)

    def run_chat_mode(self):
        """Run interactive chat mode using the UnifiedAgent."""
        if not self.unified_agent:
            logger.error("✗ UnifiedAgent not initialized. Cannot start chat mode.")
            sys.exit(1)

        print("\n" + "="*60)
        print(f"💬 Unified Agent Chat Mode - Type 'exit' to quit")
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

            # Run the agent with the user's query
            if self._runner:
                result = self._runner.run(self.run_agentic_rag(question))
            else:
                result = asyncio.run(self.run_agentic_rag(question))

            # Display the result
            if result['status'] == 'success':
                print('\nAI:\n' + result.get('result', 'No result returned.') + '\n')
            else:
                error_message = result.get('error', 'An unknown error occurred.')
                print('\nAI (Error):\n' + error_message + '\n')

    def run_gui_mode(self):
        """Run GUI mode if available."""
        try:
            from ChatGUI import run_gui
            logger.info("🖥️ Launching GUI...")
            run_gui(self.unified_agent, self._runner)
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
        if getattr(self, '_runner', None):
            try:
                self._runner.close()
            except Exception:
                pass


class AsyncRunner:
    """Run asyncio coroutines on a dedicated background loop in another thread.

    Use `run(coro)` to synchronously wait for the result.
    """
    def __init__(self):
        import threading
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._start_loop, daemon=True)
        self._thread.start()

    def _start_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run(self, coro):
        if not hasattr(self, '_loop') or self._loop.is_closed():
            raise RuntimeError('Async runner loop is not available')
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result()

    def close(self):
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception:
            pass



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
    
    if interface.unified_agent is None:
        logger.error("✗ Failed to initialize the Unified Agent. Please check the logs for errors, ensure all required packages are installed, and try again. Exiting.")
        sys.exit(1)
    
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
            if interface._runner:
                result = interface._runner.run(interface.run_agentic_rag(args.query))
            else:
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
