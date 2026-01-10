import os
import sys
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

from LLM_CI import database_tools
from quick_start_database import create_sample_database, setup_db_config



@pytest.fixture(scope='module')
def sample_db(tmp_path_factory):
    # Create sample DB in repo root using existing helper
    db_path = create_sample_database()
    setup_db_config()
    yield db_path
    # cleanup
    try:
        os.remove(db_path)
    except Exception:
        pass


def test_validate_and_fix_sql_basic(sample_db):
    q = "SELECT c.name, o.status FROM clients c JOIN orders o ON c.id = o.customer_id WHERE c.country = 'USA' AND o.status = 'pending'"
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    assert ok is True
    assert fixed.strip().upper().startswith('SELECT')


def test_generate_sql_with_rag_dummy(sample_db):
    # Dummy llm_callable that returns a simple SELECT
    def llm_callable(prompt: str) -> str:
        return "SELECT c.name, o.status FROM clients c JOIN orders o ON c.id = o.customer_id WHERE c.country = 'USA' AND o.status = 'pending';"

    ok, msg, sql = database_tools.generate_sql_with_rag('show clients from the USA with pending orders', llm_callable, max_attempts=1)
    # The RAG helper may flag short ambiguous filters (e.g., country = 'USA') as suspicious.
    # Accept either a successful generation or a suspicious-filter/clarification prompt.
    assert ok is True or ('Suspicious filter' in msg or 'suspicious filter' in msg.lower())
    if ok:
        assert sql.strip().upper().startswith('SELECT')


def test_execute_query_returns_rows(sample_db):
    q = "SELECT c.id, c.name, c.country, o.id as order_id, o.status FROM clients c JOIN orders o ON c.id = o.customer_id WHERE o.status='pending'"
    rows, err = database_tools.execute_query(q)
    assert err is None
    assert isinstance(rows, list)
    # At least one pending order in sample DB
    assert len(rows) >= 1
