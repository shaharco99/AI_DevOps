#!/usr/bin/env python3
"""
CLI interface for LLM CI - Execute prompts via command line.
Supports both direct prompts and prompt files.
"""
from __future__ import annotations

import argparse
import os
import sys

from Utils import get_llm_provider, process_prompt

# Add current directory to path for imports (allows running from project root or LLM_CI directory)
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)


def main():
    parser = argparse.ArgumentParser(
        description='LLM CI CLI - Execute prompts via command line',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python LLM_CI/cli.py --prompt "Review this Python script"
  python LLM_CI/cli.py --prompt-file ./prompt.txt
  python LLM_CI/cli.py --prompt "Load test.pdf" --verbose
        """
    )

    # Mutually exclusive group for prompt input
    prompt_group = parser.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument(
        '--prompt',
        type=str,
        help='Direct prompt text to execute'
    )
    prompt_group.add_argument(
        '--prompt-file',
        type=str,
        help='Path to file containing the prompt'
    )

    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Show tool execution details (printed to stderr)'
    )

    args = parser.parse_args()

    # Get prompt text
    if args.prompt:
        prompt = args.prompt
    elif args.prompt_file:
        prompt_file = os.path.abspath(args.prompt_file)
        if not os.path.exists(prompt_file):
            print(f"Error: Prompt file '{prompt_file}' not found", file=sys.stderr)
            sys.exit(1)
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                prompt = f.read()
        except Exception as e:
            print(f"Error reading prompt file: {e}", file=sys.stderr)
            sys.exit(1)

    # Initialize LLM
    try:
        llm_provider = os.getenv('LLM_PROVIDER', '').upper()
        llm = get_llm_provider()
        if args.verbose:
            print(f"Using LLM provider: {llm_provider}\n", file=sys.stderr)
    except Exception as e:
        print(f"Error initializing LLM: {e}", file=sys.stderr)
        sys.exit(1)

    # Process prompt and print result
    try:
        response = process_prompt(prompt, llm, verbose=args.verbose, usage_mode='cli')
        print(response)
    except KeyboardInterrupt:
        print('\nInterrupted by user', file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error processing prompt: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
