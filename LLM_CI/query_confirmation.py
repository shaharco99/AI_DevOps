"""
Query confirmation and PDF generation workflow.
Handles user interaction for query approval and result export.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from typing import Optional, Tuple

from pdf_generator import format_results_as_table, generate_pdf_from_json


class QueryConfirmation:
    """Manages query confirmation dialog and PDF generation workflow."""

    @staticmethod
    def extract_sql_query(agent_response: str) -> Optional[str]:
        """
        Extract SQL query from agent response.
        Looks for <sql_query>...</sql_query> tags.

        Args:
            agent_response: The agent's response text

        Returns:
            SQL query string or None if not found
        """
        pattern = r'<sql_query>\s*(.*?)\s*</sql_query>'
        match = re.search(pattern, agent_response, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    @staticmethod
    def prompt_user_approval(query: str, database_info: str = '') -> bool:
        """
        Prompt the user to approve a SQL query before execution.

        Args:
            query: The SQL query to approve
            database_info: Optional information about the database/tables

        Returns:
            True if user approves, False otherwise
        """
        print('\n' + '=' * 80, file=sys.stderr)
        print('QUERY PREVIEW - Please Review', file=sys.stderr)
        print('=' * 80, file=sys.stderr)

        if database_info:
            print(f"\nDatabase Info: {database_info}", file=sys.stderr)

        print('\nProposed SQL Query:', file=sys.stderr)
        print('-' * 80, file=sys.stderr)
        print(query, file=sys.stderr)
        print('-' * 80, file=sys.stderr)

        while True:
            try:
                response = input('\nExecute this query? (yes/no/cancel): ').strip().lower()
                if response in ['yes', 'y']:
                    return True
                elif response in ['no', 'n']:
                    print('Query cancelled by user.', file=sys.stderr)
                    return False
                elif response in ['cancel', 'c']:
                    print('Operation cancelled.', file=sys.stderr)
                    return False
                else:
                    print("Please enter 'yes', 'no', or 'cancel'.", file=sys.stderr)
            except (EOFError, KeyboardInterrupt):
                print('\nOperation cancelled.', file=sys.stderr)
                return False

    @staticmethod
    def prompt_pdf_generation(query_results_json: str) -> bool:
        """
        Ask user if they want to generate a PDF with the results.

        Args:
            query_results_json: JSON string with query results

        Returns:
            True if user wants PDF, False otherwise
        """
        try:
            data = json.loads(query_results_json)
            row_count = data.get('row_count', 0)

            print('\n' + '=' * 80, file=sys.stderr)
            print(f"Query Results: {row_count} rows returned", file=sys.stderr)
            print('=' * 80, file=sys.stderr)

            # Show table preview
            results = data.get('results', [])
            if results:
                table_str = format_results_as_table(results)
                print(table_str, file=sys.stderr)

            print('\n' + '=' * 80, file=sys.stderr)

            while True:
                try:
                    response = input(
                        '\nWould you like to generate a PDF with these results? (yes/no): '
                    ).strip().lower()

                    if response in ['yes', 'y']:
                        return True
                    elif response in ['no', 'n']:
                        return False
                    else:
                        print("Please enter 'yes' or 'no'.", file=sys.stderr)
                except (EOFError, KeyboardInterrupt):
                    return False

        except json.JSONDecodeError:
            print('Warning: Could not parse results JSON', file=sys.stderr)
            return False

    @staticmethod
    def generate_and_save_pdf(
        query_results_json: str,
        title: str = 'Database Query Results'
    ) -> Optional[str]:
        """
        Generate and save a PDF from query results.

        Args:
            query_results_json: JSON string with query results
            title: Title for the PDF

        Returns:
            Path to generated PDF or None on error
        """
        try:
            data = json.loads(query_results_json)
            pdf_path = generate_pdf_from_json(data, title=title)

            print(f"\n✓ PDF generated successfully: {pdf_path}", file=sys.stderr)

            # Try to open the PDF
            QueryConfirmation.open_pdf(pdf_path)

            return pdf_path

        except Exception as e:
            print(f"\n✗ Error generating PDF: {e}", file=sys.stderr)
            return None

    @staticmethod
    def open_pdf(pdf_path: str) -> None:
        """
        Attempt to open the generated PDF file.

        Args:
            pdf_path: Path to the PDF file
        """
        try:
            import platform
            import subprocess

            if not os.path.exists(pdf_path):
                print(f"PDF file not found: {pdf_path}", file=sys.stderr)
                return

            system = platform.system()

            if system == 'Windows':
                subprocess.run([pdf_path], check=True, shell=False)  # safe PDF file path
            elif system == 'Darwin':  # macOS
                subprocess.run(['open', pdf_path], check=True)
            elif system == 'Linux':
                subprocess.run(['xdg-open', pdf_path], check=True)
            else:
                print(f"PDF saved to: {pdf_path}", file=sys.stderr)

        except Exception as e:
            print(f"Could not open PDF automatically: {e}", file=sys.stderr)
            print(f"PDF saved to: {pdf_path}", file=sys.stderr)


def handle_query_workflow(
    agent_response: str,
    execute_query_func,
    database_info: str = ''
) -> Tuple[Optional[str], Optional[str]]:
    """
    Complete workflow: extract query, get user approval, execute, and optionally generate PDF.

    Args:
        agent_response: The agent's response containing the proposed query
        execute_query_func: Function to execute the query (should return JSON string)
        database_info: Optional database info for the preview

    Returns:
        Tuple of (results_json, pdf_path) or (None, None) if cancelled
    """
    # Extract query
    query = QueryConfirmation.extract_sql_query(agent_response)
    if not query:
        print('Warning: No SQL query found in agent response', file=sys.stderr)
        return None, None

    # Get user approval
    if not QueryConfirmation.prompt_user_approval(query, database_info):
        return None, None

    # Execute query
    print('\nExecuting query...', file=sys.stderr)
    results_json = execute_query_func(query)

    try:
        results_data = json.loads(results_json)
        if 'error' in results_data and results_data['error']:
            logging.error(f"\nQuery Error: {results_data['error']}")
            return None, None
    except json.JSONDecodeError:
        logging.error('\nQuery Error: Invalid response format')
        return None, None

    # Show results and ask about PDF
    pdf_path = None
    if QueryConfirmation.prompt_pdf_generation(results_json):
        pdf_path = QueryConfirmation.generate_and_save_pdf(results_json)
    else:
        logging.info('\nResults displayed in terminal.')

    return results_json, pdf_path
