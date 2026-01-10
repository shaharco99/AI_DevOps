import os
import sys
from pathlib import Path
# Ensure project root is on sys.path so LLM_CI package can be imported when tests run in CI
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

from LLM_CI.pdf_generator import format_results_as_table, generate_pdf_from_results



def test_format_results_as_table_empty():
    assert format_results_as_table([]) == 'No results'


def test_generate_pdf_from_results(tmp_path):
    # Prepare small sample data
    rows = [
        {'id': 1, 'name': 'Alice', 'country': 'USA'},
        {'id': 2, 'name': 'Bob', 'country': 'Canada'},
    ]

    out_dir = tmp_path
    output_file = os.path.join(out_dir, 'test_results.pdf')

    pdf_path = generate_pdf_from_results(rows, query='SELECT id,name,country FROM customers', title='Test PDF', output_file=output_file)
    assert os.path.exists(pdf_path)
    assert os.path.isabs(pdf_path)

    # Clean up
    os.remove(pdf_path)
