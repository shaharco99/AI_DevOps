# Database Query Feature - User Guide

## Overview

The database query feature allows users to ask natural language questions about data in a database, and the AI agent will:

1. **Understand the question** - Parse what data you're looking for
2. **Generate SQL** - Create an appropriate SQL query
3. **Get approval** - Show you the query and ask for confirmation before execution
4. **Execute safely** - Run the approved query with safety checks to prevent dangerous operations
5. **Display results** - Show results in a formatted table
6. **Export to PDF** - Optionally generate a beautiful PDF with the results

## Setup & Configuration

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Key packages for database support:
- `reportlab` - PDF generation
- `psycopg2-binary` - PostgreSQL support
- `mysql-connector-python` - MySQL support
- SQLite is built-in to Python

### 2. Configure Your Database

#### Option A: Using Configuration File (Recommended)

Copy `db_config.template.json` to `db_config.json` and edit it:

**SQLite** (default, no setup needed):
```json
{
  "type": "sqlite",
  "database": "database.db"
}
```

**PostgreSQL**:
```json
{
  "type": "postgresql",
  "host": "localhost",
  "port": 5432,
  "user": "postgres",
  "password": "your_password",
  "database": "your_database"
}
```

**MySQL**:
```json
{
  "type": "mysql",
  "host": "localhost",
  "port": 3306,
  "user": "root",
  "password": "your_password",
  "database": "your_database"
}
```

#### Option B: Using Environment Variables

Set these in your `.env` file or system environment:

For SQLite:
```
DB_TYPE=sqlite
DB_PATH=database.db
```

For PostgreSQL:
```
DB_TYPE=postgresql
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_password
DB_NAME=your_database
```

For MySQL:
```
DB_TYPE=mysql
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=your_database
```

### 3. Configure PDF Output Directory (Optional)

By default, PDFs are saved to `query_results/` folder. Customize:

```bash
export PDF_OUTPUT_DIR=/path/to/your/pdf/folder
```

## Usage Examples

### Example 1: Simple Data Query

```
You: Show me all customers from the USA
```

The agent will:
1. Retrieve database schema
2. Generate: `SELECT * FROM customers WHERE country = 'USA'`
3. Ask your approval
4. Execute and display results
5. Offer to save as PDF

### Example 2: Aggregation Query

```
You: How many orders did each customer place?
```

The agent will create a query like:
```sql
SELECT customer_id, customer_name, COUNT(*) as order_count
FROM orders
GROUP BY customer_id, customer_name
ORDER BY order_count DESC
```

### Example 3: With Conditions

```
You: Show me all employees hired in 2023 earning more than $60,000
```

The agent will generate:
```sql
SELECT * FROM employees
WHERE YEAR(hire_date) = 2023 AND salary > 60000
ORDER BY salary DESC
```

### Example 4: Multi-table Join

```
You: Show me each order with the customer name and total amount
```

The agent will create a JOIN query:
```sql
SELECT o.order_id, c.customer_name, o.order_date, o.total_amount
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
ORDER BY o.order_date DESC
```

## Interactive Workflow

### Step 1: Query Preview & Approval

When you ask a database question:

```
================================================================================
QUERY PREVIEW - Please Review
================================================================================

Proposed SQL Query:
--------------------------------------------------------------------------------
SELECT * FROM employees WHERE salary > 50000 ORDER BY salary DESC
--------------------------------------------------------------------------------

Execute this query? (yes/no/cancel):
```

- **Type `yes` or `y`** to execute
- **Type `no` or `n`** to reject and ask for a different query
- **Type `cancel` or `c`** to abort

### Step 2: View Results

After execution, results are displayed as a formatted table:

```
================================================================================
Query Results: 25 rows returned
================================================================================
+----+-------------------+----------+-------+
| id | name              | position | salary|
+----+-------------------+----------+-------+
|  1 | John Doe          | Manager  | 75000 |
|  2 | Jane Smith        | Developer| 65000 |
...
```

### Step 3: Export to PDF (Optional)

After viewing results:

```
Would you like to generate a PDF with these results? (yes/no): yes

✓ PDF generated successfully: query_results/query_results_20240115_143025.pdf
```

The PDF will be:
- Automatically opened in your default PDF viewer
- Formatted with the query, metadata, and results in a professional table
- Saved in the `query_results/` folder for future reference

## Safety Features

The system includes built-in safety measures:

### Protected Operations
The following dangerous operations are **blocked** to prevent accidental data loss:

- `DROP` - Database/table deletion
- `TRUNCATE` - Table clearing
- `DELETE` - Data deletion (use CLI for necessary deletions)
- `ALTER` - Schema modification
- `CREATE` - Table/database creation

### SQL Injection Prevention

- Queries are validated before execution
- Common injection patterns are detected and blocked
- Always use the agent's query generation for safety

### Safe Read-Only by Default

The tool is primarily designed for SELECT queries (reading data). Administrative or destructive operations require direct database access for security reasons.

## Tips & Best Practices

### 1. Be Specific with Questions

**Good:** "Show me sales from Q4 2023 with amounts over $1000"
**Vague:** "Show me sales data"

### 2. Mention Data Relationships

If your question involves joining tables:
- Mention the tables you want data from
- The agent will build the appropriate joins

### 3. Use Business Language

The agent understands business terms:
- "revenue" instead of "total_amount"
- "created date" instead of "timestamp"
- "headquarters" instead of "hq_location"

### 4. Ask for Formatting

```
You: Top 10 employees by salary, sorted highest to lowest
You: Count of orders by month in 2024
You: List unique departments
```

### 5. Chain Multiple Queries

Ask follow-up questions based on previous results:

```
You: Show me the top 5 customers by purchase amount
[Results shown]
You: Now show me all orders from customer #3
```

## Troubleshooting

### Database Connection Issues

**Error: "Failed to connect to database"**

1. Check `db_config.json` or environment variables
2. Verify database server is running
3. Confirm credentials are correct
4. For remote databases, check network connectivity

### Query Errors

**Error: "Table not found"**

Ask the agent:
```
What tables are available in this database?
```

**Error: "Column not found"**

Ask for schema information:
```
Show me the structure of the employees table
```

### PDF Generation Issues

**Error: "Could not open PDF automatically"**

- PDF is still generated in `query_results/` folder
- Open it manually with your PDF viewer
- Ensure ReportLab is installed: `pip install reportlab`

### Permission Denied

The database user may not have SELECT permissions. Contact your database administrator to grant:

```sql
GRANT SELECT ON database.* TO 'username'@'host';
```

## Advanced Features

### Get Database Schema

Ask the agent directly:

```
You: What's the database structure?
You: Show me all available tables
You: Describe the orders table
```

### Complex Analytics

The agent can handle:

- **Aggregations**: GROUP BY, COUNT, SUM, AVG, MAX, MIN
- **Filtering**: WHERE, HAVING, BETWEEN, IN
- **Sorting**: ORDER BY, multi-column sorting
- **Joins**: INNER, LEFT, RIGHT joins
- **Subqueries**: Nested queries for complex questions
- **Date functions**: Year, month, day extraction
- **String functions**: LIKE, concatenation

### Exporting Results

After saving to PDF, you can:

- **Print** the PDF for physical copies
- **Share** via email
- **Store** in document management systems
- **Convert** to other formats using PDF tools

## Python API (Advanced)

If you want to use the database tools programmatically:

```python
from database_tools import execute_database_query, get_database_schema
import json

# Get schema
schema = get_database_schema.invoke({})
print(schema)

# Execute query
query = "SELECT * FROM customers WHERE country = 'USA' LIMIT 10"
result_json = execute_database_query.invoke({"sql_query": query})
result = json.loads(result_json)

if result.get('success'):
    for row in result['results']:
        print(row)
```

## Support for Multiple Database Types

### SQLite (Default)
- File-based, no server needed
- Perfect for development and testing
- Limited concurrency

### PostgreSQL
- Enterprise-grade
- ACID compliant
- Complex query support
- Excellent for production

### MySQL
- Fast for read-heavy workloads
- Scalable
- Wide hosting support

## Performance Considerations

- The agent previews queries before execution
- Large result sets (10,000+ rows) may take time to process and export to PDF
- For very large exports, consider filtering to smaller result sets first
- Database indexes can significantly improve query performance

## Integration with Chat Interface

The database features work seamlessly with the GUI chat and CLI:

**In ChatGUI.py:**
```
You: "What's our customer base like?"
[Agent generates and executes query]
[Results displayed in chat]
[PDF save option available]
```

**In CLI:**
```bash
python cli.py --prompt "Show me sales by region"
```

## Feedback & Refinement

If the agent generates an incorrect query:

1. Say "**no**" when prompted for approval
2. Ask a follow-up question clarifying what you want
3. The agent will refine the query based on feedback

Example:
```
You: Show me all customers
[Agent: Generated query]
You: Actually, I only want active customers from this year
[Agent: Refines query]
You: Perfect! Execute it
```

---

For more information about the AI assistant capabilities, see the main README.md
