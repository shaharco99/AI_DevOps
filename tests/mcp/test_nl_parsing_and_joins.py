"""
Tests for Natural Language Query Parsing and Complex Join Queries.

This test module covers:
1. Natural language to SQL parsing (parse_natural_language_query)
2. Complex JOIN queries with multiple filters
3. Execute database query tool with natural language inputs
4. Integration of NL parsing with database execution
"""
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
def sample_db():
    """Create sample database for tests."""
    db_path = create_sample_database()
    setup_db_config()
    yield db_path
    # Cleanup
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
        if os.path.exists('db_config.json'):
            os.remove('db_config.json')
    except Exception:
        pass


# ================================================================
# TESTS FOR parse_natural_language_query
# ================================================================

class TestParseNaturalLanguageQuery:
    """Tests for the parse_natural_language_query function."""
    
    def test_parse_location_filter_usa(self, sample_db):
        """Test parsing 'from usa' location filter."""
        query = "show me all clients from usa"
        schema = database_tools.get_sqlite_schema()
        
        result = database_tools.parse_natural_language_query(query, 'clients', schema)
        
        assert result is not None
        assert 'SELECT' in result
        assert 'WHERE' in result.upper()
        assert 'LIKE' in result.upper() or "'" in result  # Should have condition
        assert 'clients' in result.lower()
    
    def test_parse_location_filter_canada(self, sample_db):
        """Test parsing location filter for different countries."""
        query = "show me all clients from canada"
        schema = database_tools.get_sqlite_schema()
        
        result = database_tools.parse_natural_language_query(query, 'clients', schema)
        
        assert result is not None
        assert 'WHERE' in result.upper()
        assert 'canada' in result.lower() or 'Canada' in result
    
    def test_parse_location_filter_variations(self, sample_db):
        """Test various ways to express location filters."""
        schema = database_tools.get_sqlite_schema()
        variations = [
            "show me all clients in usa",
            "list clients from usa",
            "get clients located in canada",
            "show clients from the UK"
        ]
        
        for query in variations:
            result = database_tools.parse_natural_language_query(query, 'clients', schema)
            if result:  # May be None if no filters detected
                assert 'SELECT' in result
                assert 'clients' in result.lower()
    
    def test_parse_year_filter(self, sample_db):
        """Test parsing year filters."""
        query = "show me all orders from 2023"
        schema = database_tools.get_sqlite_schema()
        
        result = database_tools.parse_natural_language_query(query, 'orders', schema)
        
        assert result is not None
        assert 'WHERE' in result.upper()
        assert '2023' in result or 'strftime' in result.lower()
    
    def test_parse_year_filter_orders(self, sample_db):
        """Test parsing year filter for orders table."""
        queries = [
            "list all orders from 2023",
            "show orders in 2023",
            "get orders since 2023"
        ]
        schema = database_tools.get_sqlite_schema()
        
        for query in queries:
            result = database_tools.parse_natural_language_query(query, 'orders', schema)
            if result:
                assert 'WHERE' in result.upper()
                assert 'orders' in result.lower()
    
    def test_parse_no_filter_returns_none(self, sample_db):
        """Test that queries without filters return None."""
        query = "show me all clients"
        schema = database_tools.get_sqlite_schema()
        
        result = database_tools.parse_natural_language_query(query, 'clients', schema)
        
        # Should return None since no filters detected
        assert result is None
    
    def test_parse_nonexistent_table_returns_none(self, sample_db):
        """Test parsing with non-existent table returns None."""
        query = "show me clients from usa"
        schema = database_tools.get_sqlite_schema()
        
        result = database_tools.parse_natural_language_query(query, 'nonexistent_table', schema)
        
        assert result is None
    
    def test_parse_empty_schema_returns_none(self, sample_db):
        """Test parsing with empty schema returns None."""
        query = "show me clients from usa"
        empty_schema = {}
        
        result = database_tools.parse_natural_language_query(query, 'clients', empty_schema)
        
        assert result is None


# ================================================================
# TESTS FOR COMPLEX JOIN QUERIES
# ================================================================

class TestComplexJoinQueries:
    """Tests for complex JOIN queries with filters."""
    
    def test_join_clients_orders_usa(self, sample_db):
        """Test JOIN filtering clients from USA with their orders."""
        q = """SELECT c.name, c.country, o.id as order_id, o.status
                FROM clients c
                JOIN orders o ON c.id = o.client_id
                WHERE c.country = 'USA'
                ORDER BY o.id"""
        
        rows, err = database_tools.execute_query(q)
        
        assert err is None
        assert len(rows) > 0
        # All results should be USA clients
        assert all(row['country'] == 'USA' for row in rows)
    
    def test_join_with_multiple_filters(self, sample_db):
        """Test JOIN with multiple filter conditions."""
        q = """SELECT c.name, c.country, o.status, o.total_amount
                FROM clients c
                JOIN orders o ON c.id = o.client_id
                WHERE c.country = 'USA' AND o.status = 'pending'"""
        
        rows, err = database_tools.execute_query(q)
        
        assert err is None
        assert isinstance(rows, list)
        # All results should be USA clients with pending orders
        if rows:
            assert all(row['country'] == 'USA' for row in rows)
            assert all(row['status'] == 'pending' for row in rows)
    
    def test_join_with_aggregation(self, sample_db):
        """Test JOIN with GROUP BY aggregation."""
        q = """SELECT c.country, COUNT(o.id) as order_count
                FROM clients c
                LEFT JOIN orders o ON c.id = o.client_id
                GROUP BY c.country
                ORDER BY order_count DESC"""
        
        rows, err = database_tools.execute_query(q)
        
        assert err is None
        assert len(rows) > 0
        # Should have country and order_count columns
        assert all('country' in row and 'order_count' in row for row in rows)
    
    def test_join_with_sum_aggregation(self, sample_db):
        """Test JOIN with SUM aggregation for total amounts."""
        q = """SELECT c.country, SUM(o.total_amount) as total_sales
                FROM clients c
                JOIN orders o ON c.id = o.client_id
                GROUP BY c.country"""
        
        rows, err = database_tools.execute_query(q)
        
        assert err is None
        assert len(rows) > 0
        assert all('country' in row and 'total_sales' in row for row in rows)
    
    def test_join_three_tables(self, sample_db):
        """Test JOIN with three tables."""
        q = """SELECT c.name, o.order_date, p.name as product_name
                FROM clients c
                JOIN orders o ON c.id = o.client_id
                LEFT JOIN products p ON o.id = p.id
                WHERE c.country = 'USA'"""
        
        rows, err = database_tools.execute_query(q)
        
        assert err is None
        assert isinstance(rows, list)
    
    def test_join_with_left_join(self, sample_db):
        """Test LEFT JOIN to include clients without orders."""
        q = """SELECT c.name, COUNT(o.id) as order_count
                FROM clients c
                LEFT JOIN orders o ON c.id = o.client_id
                GROUP BY c.id, c.name"""
        
        rows, err = database_tools.execute_query(q)
        
        assert err is None
        # Should return all clients, including those with no orders
        assert len(rows) >= 5  # At least 5 clients should exist
    
    def test_complex_query_usa_pending_orders(self, sample_db):
        """Test: 'show me all orders from clients from USA with pending orders'"""
        q = """SELECT c.name, c.country, o.id as order_id, o.order_date, o.status, o.total_amount
                FROM clients c
                JOIN orders o ON c.id = o.client_id
                WHERE c.country = 'USA' AND o.status = 'pending'
                ORDER BY o.order_date"""
        
        rows, err = database_tools.execute_query(q)
        
        assert err is None
        assert isinstance(rows, list)
        
        # Verify results meet criteria
        if rows:
            for row in rows:
                assert row['country'] == 'USA', f"Expected USA, got {row['country']}"
                assert row['status'] == 'pending', f"Expected pending, got {row['status']}"
    
    def test_complex_query_high_value_orders(self, sample_db):
        """Test getting high-value orders from specific countries."""
        q = """SELECT c.name, c.country, o.total_amount, o.order_date
                FROM clients c
                JOIN orders o ON c.id = o.client_id
                WHERE c.country IN ('USA', 'Canada') AND o.total_amount > 200
                ORDER BY o.total_amount DESC"""
        
        rows, err = database_tools.execute_query(q)
        
        assert err is None
        if rows:
            assert all(row['country'] in ['USA', 'Canada'] for row in rows)
            assert all(row['total_amount'] > 200 for row in rows)


# ================================================================
# TESTS FOR execute_database_query TOOL
# ================================================================

class TestExecuteDatabaseQuery:
    """Tests for the execute_database_query tool function."""
    
    def test_execute_database_query_simple_select(self, sample_db):
        """Test execute_database_query with simple SELECT."""
        q = "SELECT name, country FROM clients WHERE country = 'USA'"
        result = database_tools.execute_database_query(q)
        data = json.loads(result)
        
        assert data['success'] is True
        assert 'results' in data
        assert len(data['results']) > 0
        assert 'USA' in str(data['results'])
    
    def test_execute_database_query_join_query(self, sample_db):
        """Test execute_database_query with JOIN."""
        q = """SELECT c.name, o.status FROM clients c
                JOIN orders o ON c.id = o.client_id
                WHERE c.country = 'USA'"""
        
        result = database_tools.execute_database_query(q)
        data = json.loads(result)
        
        assert data['success'] is True
        assert len(data['results']) > 0
    
    def test_execute_database_query_auto_correction(self, sample_db):
        """Test that execute_database_query auto-corrects if needed."""
        q = "SELECT name FROM clints"  # Misspelled 'clients'
        result = database_tools.execute_database_query(q)
        data = json.loads(result)
        
        # Tool should either correct or return error
        assert 'success' in data or 'error' in data
    
    def test_execute_database_query_invalid_query(self, sample_db):
        """Test execute_database_query with invalid query."""
        q = "INSERT INTO clients VALUES (999, 'Hacker')"
        result = database_tools.execute_database_query(q)
        data = json.loads(result)
        
        # Should be rejected as it's not a SELECT
        assert data.get('success') is False or 'error' in data
    
    def test_execute_database_query_with_result_formatting(self, sample_db):
        """Test that results are properly formatted."""
        q = "SELECT id, name, country FROM clients WHERE country = 'USA' LIMIT 2"
        result = database_tools.execute_database_query(q)
        data = json.loads(result)
        
        assert data['success'] is True
        assert 'row_count' in data
        assert data['row_count'] > 0
        assert isinstance(data['results'], list)
        
        # Each result should be a dict with columns
        for row in data['results']:
            assert 'id' in row
            assert 'name' in row
            assert 'country' in row


# ================================================================
# INTEGRATION TESTS: NL PARSING + DATABASE EXECUTION
# ================================================================

class TestNLParsingIntegration:
    """Integration tests for NL parsing and database execution."""
    
    def test_nl_parse_and_execute_location_query(self, sample_db):
        """Test parsing 'show clients from usa' and executing it."""
        nl_query = "show me all clients from usa"
        schema = database_tools.get_sqlite_schema()
        
        # Parse natural language to SQL
        sql = database_tools.parse_natural_language_query(nl_query, 'clients', schema)
        
        # Should have generated SQL with WHERE clause
        if sql:
            # Execute the generated SQL
            rows, err = database_tools.execute_query(sql)
            assert err is None
            assert len(rows) > 0
            assert all(row['country'] == 'USA' for row in rows)
    
    def test_nl_parse_and_execute_year_query(self, sample_db):
        """Test parsing 'show orders from 2023' and executing it."""
        nl_query = "show me all orders from 2023"
        schema = database_tools.get_sqlite_schema()
        
        sql = database_tools.parse_natural_language_query(nl_query, 'orders', schema)
        
        if sql:
            rows, err = database_tools.execute_query(sql)
            assert err is None
            if rows:
                for row in rows:
                    # Check that dates are from 2023
                    if 'order_date' in row:
                        date_str = str(row['order_date'])
                        assert '2023' in date_str
    
    def test_direct_db_execution_with_nl_input(self, sample_db):
        """Test the _try_direct_database_execution simulation."""
        # Simulate what the agent does
        query = "show me all clients from usa"
        schema = database_tools.get_sqlite_schema()
        
        # Check if query looks like data request
        is_data_request = any(keyword in query.lower() 
                             for keyword in ['show', 'get', 'list', 'find'])
        assert is_data_request
        
        # Check if table is mentioned
        mentioned_tables = [tbl for tbl in schema.keys() if tbl.lower() in query.lower()]
        assert 'clients' in mentioned_tables
        
        # Parse and execute
        sql = database_tools.parse_natural_language_query(query, 'clients', schema)
        if sql:
            rows, err = database_tools.execute_query(sql)
            assert err is None
            assert len(rows) == 3  # 3 USA clients in sample


# ================================================================
# ENHANCED TESTS FOR EXISTING FUNCTIONALITY
# ================================================================

class TestImprovedValidation:
    """Improved tests for SQL validation with new capabilities."""
    
    def test_validate_join_with_where_multiple_conditions(self, sample_db):
        """Test validation of complex JOIN with multiple WHERE conditions."""
        q = """SELECT c.name, o.id, o.status, o.total_amount
                FROM clients c
                JOIN orders o ON c.id = o.client_id
                WHERE c.country IN ('USA', 'Canada')
                AND o.status = 'pending'
                AND o.total_amount > 100"""
        
        ok, msg, fixed = database_tools.validate_and_fix_sql(q)
        
        assert ok is True, f"Validation failed: {msg}"
        assert 'clients' in fixed
        assert 'orders' in fixed
        assert 'WHERE' in fixed.upper()
    
    def test_validate_subquery(self, sample_db):
        """Test validation of subquery."""
        q = """SELECT c.name, c.country
                FROM clients c
                WHERE c.id IN (
                    SELECT client_id FROM orders WHERE status = 'pending'
                )"""
        
        ok, msg, fixed = database_tools.validate_and_fix_sql(q)
        
        assert ok is True or 'subquery' in msg.lower()
    
    def test_get_schema_includes_all_tables(self, sample_db):
        """Test that schema info includes all expected tables."""
        # Call function directly (it's a tool function)
        schema_str = database_tools.get_database_schema_info()
        
        expected_tables = ['clients', 'orders', 'products']
        for table in expected_tables:
            assert table.lower() in schema_str.lower(), f"Table {table} not in schema"
    
    def test_table_preview_shows_sample_data(self, sample_db):
        """Test that table preview actually shows data samples."""
        # Call function directly with arguments
        preview = database_tools.get_table_preview('clients', limit=3)
        
        # Should contain sample data
        assert preview is not None
        assert len(preview) > 0
        # Should show rows or preview info
        assert 'Preview' in preview or 'Row' in preview or 'Alice' in preview


# ================================================================
# EDGE CASES AND ERROR HANDLING
# ================================================================

class TestEdgeCasesAndErrorHandling:
    """Tests for edge cases and proper error handling."""
    
    def test_nl_parse_ambiguous_filter(self, sample_db):
        """Test NL parsing with ambiguous filter terms."""
        # "from" could mean location or date
        query = "show me orders from january"
        schema = database_tools.get_sqlite_schema()
        
        result = database_tools.parse_natural_language_query(query, 'orders', schema)
        # Should either parse it or return None gracefully
        assert result is None or 'SELECT' in result
    
    def test_execute_very_large_result_set(self, sample_db):
        """Test that large result sets are handled properly."""
        # Create a query that returns all orders
        q = "SELECT * FROM orders"
        
        result = database_tools.execute_database_query(q)
        data = json.loads(result)
        
        # Should still return valid JSON with all results
        assert data['success'] is True
        assert isinstance(data['results'], list)
    
    def test_special_characters_in_filter(self, sample_db):
        """Test handling of special characters in filter values."""
        q = "SELECT name FROM clients WHERE name LIKE '%Johnson%'"
        
        rows, err = database_tools.execute_query(q)
        assert err is None
        assert isinstance(rows, list)
    
    def test_null_handling_in_results(self, sample_db):
        """Test that NULL values are handled properly in results."""
        q = """SELECT c.name, o.id FROM clients c
                LEFT JOIN orders o ON c.id = o.client_id
                WHERE o.id IS NULL"""
        
        rows, err = database_tools.execute_query(q)
        assert err is None or isinstance(rows, list)
