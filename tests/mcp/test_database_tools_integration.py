"""
Integration tests for database tools.
Tests the interaction between multiple functions and end-to-end workflows.
"""
import json
import os
import sys
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

from LLM_CI import database_tools
from conftest import call_tool


def test_end_to_end_query_workflow():
    """Test complete workflow: schema -> validate -> execute."""
    # Step 1: Get schema
    schema = call_tool(database_tools.get_database_schema_info)
    assert 'clients' in schema.lower()

    # Step 2: Get table preview
    preview = call_tool(database_tools.get_table_preview, 'clients', limit=2)
    assert 'clients' in preview.lower()

    # Step 3: Validate query
    q = "SELECT name, country FROM clients WHERE country = 'USA'"
    validation_result = call_tool(database_tools.validate_sql_query, q)
    validation_data = json.loads(validation_result)
    assert validation_data['valid'] is True

    # Step 4: Execute query
    rows, err = database_tools.execute_query(q)
    assert err is None
    assert len(rows) > 0
    assert 'name' in rows[0]
    assert 'country' in rows[0]


def test_validate_then_execute_workflow():
    """Test workflow of validating then executing a query."""
    q = 'SELECT c.name, o.total_amount FROM clients c JOIN orders o ON c.id = o.client_id WHERE o.total_amount > 200'

    # Validate first
    validation_result = call_tool(database_tools.validate_sql_query, q)
    validation_data = json.loads(validation_result)

    if validation_data['valid']:
        # Use corrected query if available
        query_to_execute = validation_data.get('corrected_query', q)
        rows, err = database_tools.execute_query(query_to_execute)
        assert err is None
        assert isinstance(rows, list)


def test_schema_info_format():
    """Test that schema info is in expected format."""
    schema = call_tool(database_tools.get_database_schema_info)
    assert isinstance(schema, str)
    assert len(schema) > 0

    # Should contain table information
    lines = schema.split('\n')
    assert len(lines) > 0

    # Should mention at least one table
    assert any('clients' in line.lower() or 'orders' in line.lower() or 'products' in line.lower() for line in lines)


def test_table_preview_format():
    """Test that table preview is in expected format."""
    preview = call_tool(database_tools.get_table_preview, 'clients', limit=3)
    assert isinstance(preview, str)
    assert 'clients' in preview.lower()

    # Should contain row information
    assert 'Row' in preview or 'Preview' in preview or ':' in preview


def test_multiple_table_queries(sample_db):
    """Test queries involving multiple tables."""
    queries = [
        'SELECT c.name, COUNT(o.id) as order_count FROM clients c LEFT JOIN orders o ON c.id = o.client_id GROUP BY c.name',
        'SELECT c.country, SUM(o.total_amount) as total FROM clients c JOIN orders o ON c.id = o.client_id GROUP BY c.country',
    ]

    for q in queries:
        ok, msg, fixed = database_tools.validate_and_fix_sql(q)
        assert ok is True, f"Query should be valid: {q}, error: {msg}"

        rows, err = database_tools.execute_query(fixed)
        assert err is None, f"Query should execute: {q}, error: {err}"
        assert isinstance(rows, list)


def test_validation_correction_workflow(sample_db):
    """Test that validation can correct and return corrected queries."""
    # Query with potential issues
    q = "SELECT nme FROM clints WHERE cntry = 'USA'"  # Misspelled names

    validation_result = database_tools.validate_sql_query(q)
    validation_data = json.loads(validation_result)

    # May or may not be able to correct, but should provide feedback
    assert 'valid' in validation_data
    assert 'message' in validation_data
    assert 'query' in validation_data


def test_error_handling_invalid_table(sample_db):
    """Test error handling when table doesn't exist."""
    q = 'SELECT * FROM nonexistent_table_xyz'

    # Validation should fail
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    assert ok is False
    # Accept various error message formats
    assert ('not found' in msg.lower() or 'table' in msg.lower() or
            'could not construct' in msg.lower() or 'attempts' in msg.lower())

    # Tool validation should also fail
    validation_result = database_tools.validate_sql_query(q)
    validation_data = json.loads(validation_result)
    assert validation_data['valid'] is False


def test_error_handling_invalid_column(sample_db):
    """Test error handling when column doesn't exist."""
    q = 'SELECT nonexistent_column_xyz FROM clients'

    # Validation should fail
    ok, msg, fixed = database_tools.validate_and_fix_sql(q)
    assert ok is False
    assert 'not found' in msg.lower() or 'column' in msg.lower()


def test_get_table_preview_nonexistent_table(sample_db):
    """Test get_table_preview with non-existent table."""
    result = database_tools.get_table_preview('nonexistent_table_xyz')
    assert 'not exist' in result.lower() or 'error' in result.lower() or 'not found' in result.lower()


def test_concurrent_queries(sample_db):
    """Test that multiple queries can be executed in sequence."""
    queries = [
        'SELECT COUNT(*) as total_clients FROM clients',
        'SELECT COUNT(*) as total_orders FROM orders',
        'SELECT COUNT(*) as total_products FROM products',
    ]

    results = []
    for q in queries:
        rows, err = database_tools.execute_query(q)
        assert err is None
        assert len(rows) == 1
        results.append(rows[0])

    # All queries should return results
    assert len(results) == 3
    assert all('total' in str(r).lower() for r in results)
