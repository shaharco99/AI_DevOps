"""
Quick Start Example - Using Database Features

This script demonstrates how to use the database query feature
with a simple SQLite example database.
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

# Add LLM_CI to path
llm_ci_path = Path(__file__).parent / 'LLM_CI'
sys.path.insert(0, str(llm_ci_path))


def create_sample_database():
    """Create a sample SQLite database with sample data for testing."""
    db_path = 'sample_database.db'

    # Remove existing database
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create tables
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

    print(f"✓ Sample database created: {db_path}")
    return db_path


def setup_db_config():
    """Create db_config.json for the sample database."""
    config = {
        'type': 'sqlite',
        'database': 'sample_database.db'
    }

    with open('db_config.json', 'w') as f:
        json.dump(config, f, indent=2)

    print('✓ Database configuration created: db_config.json')


def example_queries():
    """Show example queries you can ask the agent."""
    examples = """
EXAMPLE QUERIES TO TRY:

1. Basic Selection:
   "Show me all active clients"
   "List all orders from the USA"

2. Aggregations:
   "How many orders did each client place?"
   "What's the total revenue by country?"
   "Show average order value per client"

3. Filtering & Sorting:
   "Show me orders worth more than $200, sorted by amount"
   "List clients from USA, ordered by name"

4. Date-based:
   "Show me orders from July 2023"
   "Which clients were added this year?"

5. Joins:
   "Show me each order with the client name and email"
   "List clients with their total order amounts"

6. Complex:
   "Show clients from USA who spent more than $300"
   "Top 3 clients by number of orders"
   "Products in stock and their categories"

After each query:
- Review the generated SQL
- Approve or reject the query
- View the results
- Optionally generate a PDF

TIP: Be conversational! The AI understands business language like
"revenue", "created date", "headquarters", etc.
"""
    print(examples)


def main():
    print('=' * 80)
    print('DATABASE FEATURE - QUICK START EXAMPLE')
    print('=' * 80)

    # Step 1: Create sample database
    print('\n[1/3] Setting up sample database...')
    db_path = create_sample_database()

    # Step 2: Create configuration
    print('\n[2/3] Creating database configuration...')
    setup_db_config()

    # Step 3: Show instructions
    print('\n[3/3] Ready to use!')
    print('\n' + '=' * 80)
    print('NEXT STEPS:')
    print('=' * 80)
    print('\n1. Run the chat interface:')
    print('   python LLM_CI/Chat.py')
    print('\n2. Or use the GUI:')
    print('   python LLM_CI/ChatGUI.py')
    print('\n3. Try asking database questions!')

    print('\n' + '=' * 80)
    print('DATABASE INFORMATION:')
    print('=' * 80)
    print(f"Database file: {db_path}")
    print('\nTables:')
    print('  - clients (id, name, email, country, created_date, is_active)')
    print('  - orders (id, client_id, order_date, total_amount, status)')
    print('  - products (id, name, category, price, stock)')

    example_queries()

    print('\n' + '=' * 80)
    print('For detailed documentation, see: DATABASE_FEATURE_GUIDE.md')
    print('=' * 80)


if __name__ == '__main__':
    main()
