import sys
from pathlib import Path

from LLM_CI.Utils import format_results_as_markdown

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))


def test_format_results_markdown_basic():
    rows = [
        {'id': 1, 'name': 'Alice'},
        {'id': 2, 'name': 'Bob'},
    ]
    md = format_results_as_markdown(rows, max_rows=10)
    assert '|' in md and 'id' in md and 'name' in md
    assert 'Alice' in md and 'Bob' in md
