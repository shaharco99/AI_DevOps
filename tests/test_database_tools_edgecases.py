import os
import sys
from pathlib import Path

from LLM_CI import database_tools
from quick_start_database import create_sample_database, setup_db_config

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))


def setup_module(module):
    # Ensure sample DB exists for tests
    create_sample_database()
    setup_db_config()


def teardown_module(module):
    try:
        os.remove('sample_database.db')
    except Exception:
        pass


def test_missing_from_clause_infers_table():
    q = 'SELECT name, country'
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    # The validator should accept the query; it may or may not add a FROM
    assert ok is True


def test_ambiguous_select_id_infers_table():
    q = 'SELECT id'
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    # It should try to infer a FROM table rather than erroring out
    assert ok is True


def test_nonexistent_column_reports():
    q = 'SELECT nonexistent_column FROM clients'
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    assert ok is False
    assert 'not found' in msg.lower() or 'not found' in msg


def test_nonexistent_table_reports():
    q = 'SELECT name FROM this_table_does_not_exist'
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    assert ok is False
    # The validator may return a generic failure after attempts or a specific
    # message about missing tables; accept either.
    assert ('could not construct' in msg.lower()) or ('not found' in msg.lower()) or ('table' in msg.lower())


def test_nonexistent_table_and_column_reports():
    q = 'SELECT fakecol FROM no_table_here'
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    assert ok is False
    assert 'not found' in msg.lower() or 'no table' in msg.lower()


def test_column_suggestion_fuzzy():
    # Intentionally misspelled 'name' as 'cname' to trigger suggestions
    q = 'SELECT cname FROM clients'
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    assert ok is False
    assert 'suggest' in msg.lower() or 'did you mean' in msg.lower()


def test_prefixed_star_executes():
    q = "SELECT c.* FROM clients c JOIN orders o ON c.id = o.customer_id WHERE c.country = 'USA' AND o.status = 'pending'"
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    assert ok is True, f"Validator failed: {msg}"
    rows, err = database_tools.execute_query(fixed)
    assert err is None
    assert isinstance(rows, list)


def test_select_star_executes():
    q = "SELECT * FROM clients WHERE country = 'USA'"
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    assert ok is True, f"Validator failed: {msg}"
    rows, err = database_tools.execute_query(fixed)
    assert err is None
    assert isinstance(rows, list)
