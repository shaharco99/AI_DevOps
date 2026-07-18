"""
Pytest configuration for database tests.
This ensures proper setup and teardown of test databases.
"""

import json
import os
import sys
import sqlite3
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))


def pytest_configure(config):
    """Setup test environment before running tests."""
    # Create test database before anything imports database_tools
    os.chdir(repo_root)
    create_test_database()


def create_test_database():
    """Create an isolated test database."""
    # Use a test-specific database path
    db_path = 'test_database.db'
    
    # Remove existing test database
    if os.path.exists(db_path):
        os.remove(db_path)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create tables with sample data
    cursor.execute('''
    CREATE TABLE clients (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT,
        country TEXT,
        created_date DATE,
        is_active INTEGER
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE orders (
        id INTEGER PRIMARY KEY,
        client_id INTEGER,
        order_date DATE,
        total_amount DECIMAL(10, 2),
        status TEXT,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE products (
        id INTEGER PRIMARY KEY,
        name TEXT,
        category TEXT,
        price DECIMAL(10, 2),
        stock INTEGER
    )
    ''')
    
    # Insert sample data - clients
    clients = [
        (1, 'Alice Johnson', 'alice@example.com', 'USA', '2023-01-15', 1),
        (2, 'Bob Smith', 'bob@example.com', 'Canada', '2023-02-20', 1),
        (3, 'Carol White', 'carol@example.com', 'USA', '2023-03-10', 1),
        (4, 'David Brown', 'david@example.com', 'UK', '2023-01-25', 0),
        (5, 'Eve Davis', 'eve@example.com', 'USA', '2023-04-05', 1),
    ]
    cursor.executemany('INSERT INTO clients VALUES (?, ?, ?, ?, ?, ?)', clients)
    
    # Insert sample data - Orders
    orders = [
        (1, 1, '2023-06-01', 250.00, 'completed'),
        (2, 1, '2023-07-15', 125.50, 'completed'),
        (3, 2, '2023-06-10', 500.00, 'completed'),
        (4, 3, '2023-07-20', 75.25, 'pending'),
        (5, 3, '2023-08-01', 300.00, 'completed'),
        (6, 5, '2023-08-05', 450.75, 'completed'),
        (7, 2, '2023-08-10', 200.00, 'processing'),
    ]
    cursor.executemany('INSERT INTO orders VALUES (?, ?, ?, ?, ?)', orders)
    
    # Insert sample data - Products
    products = [
        (1, 'Laptop', 'Electronics', 999.99, 5),
        (2, 'Mouse', 'Electronics', 29.99, 50),
        (3, 'Keyboard', 'Electronics', 79.99, 20),
        (4, 'Monitor', 'Electronics', 299.99, 8),
        (5, 'Coffee Maker', 'Appliances', 49.99, 15),
    ]
    cursor.executemany('INSERT INTO products VALUES (?, ?, ?, ?, ?)', products)
    
    conn.commit()
    conn.close()
    
    # Create db_config.json pointing to test database
    config = {
        'type': 'sqlite',
        'database': 'test_database.db'
    }
    
    with open('db_config.json', 'w') as f:
        json.dump(config, f, indent=2)


def call_tool(tool_func, *args, **kwargs):
    """Helper to call both StructuredTool and regular functions.
    
    This function handles:
    - Regular functions: calls them directly
    - Decorated tools with original function: uses _original_func
    - StructuredTool objects: uses invoke() method
    """
    if hasattr(tool_func, '_original_func'):
        # It's a decorated tool with original function stored
        return tool_func._original_func(*args, **kwargs)
    elif hasattr(tool_func, 'invoke'):
        # It's a StructuredTool - use invoke with input dict
        # Build input dict from function signature
        import inspect
        sig = inspect.signature(tool_func.func)
        param_names = list(sig.parameters.keys())
        input_dict = dict(zip(param_names, args))
        input_dict.update(kwargs)
        result = tool_func.invoke(input_dict)
        return result
    else:
        # Regular function
        return tool_func(*args, **kwargs)


@pytest.fixture(scope='function', autouse=True)
def reset_database_tools():
    """Reset database_tools module state between tests."""
    # Import after conftest runs so config is ready
    try:
        from LLM_CI import database_tools
        
        # Reset module globals
        database_tools._db_config = None
        database_tools._db_connection = None
        database_tools._engine = None
        
        yield
        
        # Cleanup after test
        database_tools.close_db_connection()
        database_tools._db_config = None
        database_tools._db_connection = None
        database_tools._engine = None
    except ImportError:
        yield


def pytest_sessionfinish(session, exitstatus):
    """Cleanup after all tests."""
    os.chdir(repo_root)
    # Remove test database
    if os.path.exists('test_database.db'):
        try:
            os.remove('test_database.db')
        except Exception:
            pass
    # Remove test config
    if os.path.exists('db_config.json'):
        try:
            os.remove('db_config.json')
        except Exception:
            pass
