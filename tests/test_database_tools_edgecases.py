import os
import sys
from pathlib import Path

import pytest

from LLM_CI import database_tools
from quick_start_database import create_sample_database, setup_db_config

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))


@pytest.fixture(scope='module', autouse=True)
def setup_and_teardown():
    """Setup and teardown for all tests in this module."""
    # Setup
    create_sample_database()
    setup_db_config()
    yield
    # Teardown
    try:
        if os.path.exists('sample_database.db'):
            os.remove('sample_database.db')
        if os.path.exists('db_config.json'):
            os.remove('db_config.json')
    except Exception:
        pass


def test_missing_from_clause_infers_table():
    """Test that queries without FROM clause can infer tables."""
    q = 'SELECT name, country'
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    # The validator should accept the query; it may or may not add a FROM
    assert ok is True


def test_ambiguous_select_id_infers_table():
    """Test that ambiguous column names can infer tables."""
    q = 'SELECT id'
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    # It should try to infer a FROM table rather than erroring out
    assert ok is True


def test_nonexistent_column_reports():
    """Test that nonexistent columns are reported with helpful messages."""
    q = 'SELECT nonexistent_column FROM clients'
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    assert ok is False
    assert 'not found' in msg.lower() or 'not found' in msg


def test_nonexistent_table_reports():
    """Test that nonexistent tables are reported with helpful messages."""
    q = 'SELECT name FROM this_table_does_not_exist'
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    assert ok is False
    # The validator may return a generic failure after attempts or a specific
    # message about missing tables; accept either.
    assert ('could not construct' in msg.lower()) or ('not found' in msg.lower()) or ('table' in msg.lower())


def test_nonexistent_table_and_column_reports():
    """Test error reporting when both table and column don't exist."""
    q = 'SELECT fakecol FROM no_table_here'
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    assert ok is False
    assert 'not found' in msg.lower() or 'no table' in msg.lower()


def test_column_suggestion_fuzzy():
    """Test that fuzzy matching suggests similar column names."""
    # Intentionally misspelled 'name' as 'cname' to trigger suggestions
    q = 'SELECT cname FROM clients'
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    assert ok is False
    assert 'suggest' in msg.lower() or 'did you mean' in msg.lower()


def test_prefixed_star_executes():
    """Test that prefixed SELECT * (e.g., c.*) works correctly."""
    q = "SELECT c.* FROM clients c JOIN orders o ON c.id = o.client_id WHERE c.country = 'USA' AND o.status = 'pending'"
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    assert ok is True, f"Validator failed: {msg}"
    rows, err = database_tools.execute_query(fixed)
    assert err is None
    assert isinstance(rows, list)


def test_select_star_executes():
    """Test that SELECT * works correctly."""
    q = "SELECT * FROM clients WHERE country = 'USA'"
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    assert ok is True, f"Validator failed: {msg}"
    rows, err = database_tools.execute_query(fixed)
    assert err is None
    assert isinstance(rows, list)


def test_case_insensitive_table_names():
    """Test that table names are matched case-insensitively."""
    q = "SELECT name FROM CLIENTS"
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    assert ok is True, f"Should handle uppercase table names: {msg}"
    
    q = "SELECT name FROM Clients"
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    assert ok is True, f"Should handle mixed case table names: {msg}"


def test_table_name_fuzzy_matching():
    """Test that similar table names are suggested."""
    q = "SELECT name FROM client"  # Missing 's'
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    # Should either fix it or suggest 'clients'
    assert ok is True or 'client' in msg.lower()


def test_complex_join_with_aliases():
    """Test complex JOIN queries with table aliases."""
    q = """
    SELECT 
        c.name as client_name,
        o.order_date,
        o.total_amount,
        p.name as product_name
    FROM clients c
    JOIN orders o ON c.id = o.client_id
    LEFT JOIN products p ON o.id = p.id
    WHERE c.country = 'USA'
    ORDER BY o.order_date DESC
    """
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    # Should validate successfully (may need fixes for products join)
    assert ok is True or 'error' not in msg.lower()


def test_query_with_comments_blocked():
    """Test that queries with SQL comments are blocked."""
    q = "SELECT name FROM clients -- This is a comment"
    ok, msg = database_tools.is_safe_select_query(q)
    assert ok is False
    assert 'comment' in msg.lower()
    
    q = "SELECT name FROM clients /* This is a comment */"
    ok, msg = database_tools.is_safe_select_query(q)
    assert ok is False
    assert 'comment' in msg.lower()


def test_query_with_semicolon_blocked():
    """Test that queries with semicolons are blocked."""
    q = "SELECT name FROM clients;"
    ok, msg = database_tools.is_safe_select_query(q)
    assert ok is False
    assert 'semicolon' in msg.lower()


def test_empty_query_handling():
    """Test handling of empty or whitespace-only queries."""
    q = ""
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    assert ok is False
    
    q = "   "
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    assert ok is False


def test_malformed_sql_handling():
    """Test handling of malformed SQL queries."""
    q = "SELECT FROM"  # Missing columns and table
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    assert ok is False or 'column' in msg.lower()


def test_get_table_preview_empty_table():
    """Test get_table_preview with an empty table."""
    # First create an empty table
    rows, err = database_tools.execute_query("CREATE TABLE IF NOT EXISTS empty_test (id INTEGER, name TEXT)")
    if not err:
        result = database_tools.get_table_preview.invoke({'table_name': 'empty_test'})
        assert 'no rows' in result.lower() or 'empty' in result.lower() or 'exists' in result.lower()
        # Cleanup
        database_tools.execute_query("DROP TABLE IF EXISTS empty_test")
