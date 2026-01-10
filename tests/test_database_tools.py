import json
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
        if os.path.exists('db_config.json'):
            os.remove('db_config.json')
    except Exception:
        pass


def test_validate_and_fix_sql_basic(sample_db):
    """Test basic SQL validation and fixing with a valid query."""
    # Use a simpler query first to ensure basic validation works
    q = "SELECT name, country FROM clients WHERE country = 'USA'"
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    assert ok is True, f"Simple validation failed with message: {msg}"
    assert fixed.strip().upper().startswith('SELECT')
    assert 'clients' in fixed

    # Now test a JOIN query
    q2 = "SELECT c.name, o.status FROM clients c JOIN orders o ON c.id = o.client_id WHERE c.country = 'USA' AND o.status = 'pending'"
    ok2, msg2, fixed2 = database_tools.validate_and_fix_sql(q2)
    assert ok2 is True, f"JOIN validation failed with message: {msg2}"
    assert fixed2.strip().upper().startswith('SELECT')
    assert 'clients' in fixed2
    assert 'orders' in fixed2


def test_execute_query_returns_rows(sample_db):
    """Test that execute_query returns rows correctly."""
    q = "SELECT c.id, c.name, c.country, o.id as order_id, o.status FROM clients c JOIN orders o ON c.id = o.client_id WHERE o.status='pending'"
    rows, err = database_tools.execute_query(q)
    assert err is None
    assert isinstance(rows, list)
    # At least one pending order in sample DB
    assert len(rows) >= 1
    # Check structure of returned rows
    assert isinstance(rows[0], dict)
    assert 'name' in rows[0] or 'order_id' in rows[0]


def test_get_database_schema_info(sample_db):
    """Test the get_database_schema_info tool function."""
    result = database_tools.get_database_schema_info.invoke({})
    assert isinstance(result, str)
    assert 'clients' in result.lower()
    assert 'orders' in result.lower()
    assert 'products' in result.lower()
    assert 'id' in result.lower() or 'name' in result.lower()


def test_get_table_preview(sample_db):
    """Test the get_table_preview tool function."""
    result = database_tools.get_table_preview.invoke({'table_name': 'clients', 'limit': 3})
    assert isinstance(result, str)
    assert 'clients' in result.lower()
    assert 'Preview' in result or 'Row' in result

    # Test with non-existent table
    result = database_tools.get_table_preview.invoke({'table_name': 'nonexistent_table'})
    assert 'not exist' in result.lower() or 'error' in result.lower()


def test_validate_sql_query_tool_valid(sample_db):
    """Test validate_sql_query tool with a valid query."""
    q = "SELECT name, country FROM clients WHERE country = 'USA'"
    result = database_tools.validate_sql_query.invoke({'sql_query': q})
    data = json.loads(result)
    assert data['valid'] is True
    assert 'query' in data
    assert data['query'] == q


def test_validate_sql_query_tool_invalid(sample_db):
    """Test validate_sql_query tool with an invalid query."""
    q = 'SELECT nonexistent_column FROM clients'
    result = database_tools.validate_sql_query.invoke({'sql_query': q})
    data = json.loads(result)
    assert data['valid'] is False
    assert 'message' in data
    assert 'not found' in data['message'].lower() or 'error' in data['message'].lower()


def test_validate_sql_query_tool_unsafe(sample_db):
    """Test validate_sql_query tool with an unsafe query (INSERT)."""
    q = "INSERT INTO clients (name) VALUES ('Test')"
    result = database_tools.validate_sql_query.invoke({'sql_query': q})
    data = json.loads(result)
    assert data['valid'] is False
    assert 'not permitted' in data['message'].lower() or 'only select' in data['message'].lower()


def test_is_safe_select_query_valid(sample_db):
    """Test is_safe_select_query with valid SELECT queries."""
    valid_queries = [
        'SELECT * FROM clients',
        'SELECT name FROM clients WHERE id = 1',
        'PRAGMA table_info(clients)',
    ]
    for q in valid_queries:
        ok, msg = database_tools.is_safe_select_query(q)
        assert ok is True, f"Query should be safe: {q}"


def test_is_safe_select_query_forbidden(sample_db):
    """Test is_safe_select_query with forbidden operations."""
    forbidden_queries = [
        "INSERT INTO clients VALUES (1, 'Test')",
        "UPDATE clients SET name = 'Test'",
        'DELETE FROM clients',
        'DROP TABLE clients',
    ]
    for q in forbidden_queries:
        ok, msg = database_tools.is_safe_select_query(q)
        assert ok is False, f"Query should be blocked: {q}"
        assert 'not permitted' in msg.lower() or 'only select' in msg.lower()


def test_execute_query_with_join(sample_db):
    """Test execute_query with a JOIN query."""
    q = "SELECT c.name, o.order_date, o.total_amount FROM clients c JOIN orders o ON c.id = o.client_id WHERE c.country = 'USA'"
    rows, err = database_tools.execute_query(q)
    assert err is None
    assert isinstance(rows, list)
    if rows:
        assert 'name' in rows[0]
        assert 'order_date' in rows[0] or 'total_amount' in rows[0]


def test_execute_query_aggregation(sample_db):
    """Test execute_query with aggregation functions."""
    q = 'SELECT country, COUNT(*) as client_count FROM clients GROUP BY country'
    rows, err = database_tools.execute_query(q)
    assert err is None
    assert isinstance(rows, list)
    assert len(rows) > 0
    assert 'country' in rows[0]
    assert 'client_count' in rows[0]
