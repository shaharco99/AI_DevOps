# Database Query Feature - Integration & Getting Started

## 🎯 What You Got

Your MCP project now has a complete **database query capability** where:

1. **Users ask questions** about database data in natural language
2. **The AI agent generates SQL queries** automatically
3. **The user reviews and approves** the query before execution
4. **Results are executed safely** and displayed as formatted tables
5. **PDFs can be generated** with beautiful table formatting and metadata

## 📦 Files Added to Your Project

### Core Database Modules
- `LLM_CI/database_tools.py` - Database connection and query execution
- `LLM_CI/pdf_generator.py` - PDF generation from query results
- `LLM_CI/query_confirmation.py` - User confirmation workflow

### Configuration
- `LLM_CI/db_config.template.json` - Template for database configuration
- `LLM_CI/db_config_examples.py` - Examples for different database types

### Documentation & Examples
- `DATABASE_FEATURE_GUIDE.md` - Complete user documentation
- `DATABASE_IMPLEMENTATION_SUMMARY.md` - Technical implementation details
- `quick_start_database.py` - Quick start script to set up sample DB

## 🚀 Quick Start (5 minutes)

### Step 1: Install Dependencies

```bash
cd c:\Users\shahar.cohen\source\repos\MCP
pip install -r requirements.txt
```

Key additions:
- `reportlab` - PDF generation
- `psycopg2-binary` - PostgreSQL (optional)
- `mysql-connector-python` - MySQL (optional)

### Step 2: Set Up Sample Database

```bash
python quick_start_database.py
```

This creates:
- `sample_database.db` - SQLite database with sample data
- `db_config.json` - Configuration file
- Tables: customers, orders, products

### Step 3: Test It Out

**Option A: CLI Chat**
```bash
cd LLM_CI
python Chat.py
```

**Option B: GUI**
```bash
cd LLM_CI
python ChatGUI.py
```

Then ask:
```
You: Show me all customers from the USA
```

Watch the agent:
1. Generate the SQL query
2. Show it for your review
3. Execute it after your approval
4. Display results in a table
5. Offer to save as PDF

## 🔧 Configuration for Your Database

### For SQLite (No Setup Required)

Create `LLM_CI/db_config.json`:
```json
{
  "type": "sqlite",
  "database": "path/to/your/database.db"
}
```

### For PostgreSQL

Create `LLM_CI/db_config.json`:
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

### For MySQL

Create `LLM_CI/db_config.json`:
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

### For MSSQL (SQL Server)

Create `LLM_CI/db_config.json`:
```json
{
  "type": "mssql",
  "host": "localhost",
  "port": 1433,
  "user": "sa",
  "password": "your_password",
  "database": "your_database",
  "driver": "ODBC Driver 17 for SQL Server"
}
```

**MSSQL Setup Notes:**
- Requires ODBC driver installed on your system
- Common drivers: "ODBC Driver 17 for SQL Server" (recommended) or "ODBC Driver 18 for SQL Server"
- Windows: ODBC drivers usually come pre-installed
- Linux: Install via `sudo apt-get install odbcinst unixodbc-dev` then `sudo apt-get install odbc-mssql`
- macOS: Install via `brew install unixodbc freetds`

### Alternative: Environment Variables

Add to `.env`:
```
DB_TYPE=postgresql
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_password
DB_NAME=your_database
```

Or for MSSQL:
```
DB_TYPE=mssql
DB_HOST=localhost
DB_PORT=1433
DB_USER=sa
DB_PASSWORD=your_password
DB_NAME=your_database
DB_DRIVER=ODBC Driver 17 for SQL Server
```

## 📊 Example Usage Scenarios

### Scenario 1: Sales Analytics
```
You: What are the top 5 products by sales volume?
AI: [Generates query with JOINs and GROUP BY]
Query shown: SELECT product_id, COUNT(*) as sales_count FROM orders...
You: yes
[Results displayed]
You: yes (for PDF)
✓ PDF saved and opened
```

### Scenario 2: Customer Analysis
```
You: Show me customers who haven't purchased in the last 90 days
AI: [Generates query with date filtering]
You: yes
[Results shown in table]
```

### Scenario 3: Business Report
```
You: Monthly revenue trends for 2024
AI: [Generates aggregation query]
You: yes
[Results displayed]
You: yes (for PDF)
PDF saved: query_results/query_results_20240115_143025.pdf
```

## 🛡️ Safety Features Built-In

### Blocked Operations (Protected)
- ❌ `DROP` - Table/database deletion
- ❌ `TRUNCATE` - Clear all data
- ❌ `DELETE` - Remove rows
- ❌ `ALTER` - Change schema
- ❌ `CREATE` - New tables/databases

### SQL Injection Prevention
- Automatic query validation
- Detection of injection patterns
- Safe execution environment

### User Control
- Every query requires approval before execution
- You see the exact SQL before it runs
- Can reject and ask for refined query

## 📖 Documentation Files

| File | Purpose |
|------|---------|
| `DATABASE_FEATURE_GUIDE.md` | Complete user guide with examples, troubleshooting, and best practices |
| `DATABASE_IMPLEMENTATION_SUMMARY.md` | Technical implementation details and architecture |
| `quick_start_database.py` | Automated setup script for sample database |
| `LLM_CI/db_config_examples.py` | Configuration examples and templates |

## 🔌 How It Works (Behind the Scenes)

```
User Message
    ↓
Chat Interface (Chat.py / ChatGUI.py)
    ↓
LLM Agent with Tools
    ├─ get_database_schema() - Understands what tables exist
    ├─ generate_and_preview_query() - Creates SQL query
    └─ execute_database_query() - Runs approved query
    ↓
query_confirmation.py
    ├─ Extract SQL from agent response
    ├─ Show preview to user
    └─ Wait for approval
    ↓
database_tools.py
    ├─ Connect to database (SQLite/PostgreSQL/MySQL)
    ├─ Validate query for safety
    └─ Execute and return results
    ↓
pdf_generator.py
    ├─ Format results as table
    └─ Create professional PDF with metadata
    ↓
Results Display
    ├─ ASCII table in terminal
    └─ PDF file saved and opened
```

## 🎓 Integration with Existing Features

The database feature works seamlessly with your existing tools:

### With File Tools
```
You: Load the sales report PDF and compare with database orders
AI: Uses doc_loader for file + execute_database_query for DB
```

### With Code Review
```
You: Show me the code that generated these queries and the actual schema
AI: Uses code_reviewer + get_database_schema
```

### With Chat History
```
You: Earlier we looked at customers, now show their orders
AI: Remembers context and uses database tools appropriately
```

## 🐛 Troubleshooting

### Issue: "Failed to connect to database"
**Solution:**
1. Check `db_config.json` exists in `LLM_CI/` folder
2. Verify database server is running
3. Test credentials: `psql -U user -d database` (PostgreSQL) or `mysql -u root` (MySQL)
4. Check firewall/network connectivity

### Issue: "Table not found"
**Solution:**
- Ask the agent: "What tables are available in this database?"
- Agent will show you the schema

### Issue: "PDF won't open"
**Solution:**
- PDF is still saved in `query_results/` folder
- Open manually with your PDF reader
- Ensure `reportlab` is installed: `pip install reportlab`

### Issue: Import errors when running
**Solution:**
```bash
# Reinstall dependencies
pip install --upgrade -r requirements.txt

# For PostgreSQL support
pip install psycopg2-binary

# For MySQL support
pip install mysql-connector-python

# For PDF generation
pip install reportlab
```

## 💡 Best Practices

### 1. Ask Clear Questions
```
Good:  "Show me sales over $1000 from Q4 2023"
Bad:   "Show me sales data"
```

### 2. Use Business Language
The agent understands terms like:
- "revenue" (not "total_amount")
- "created date" (not "timestamp")
- "active customers" (not "where is_active = 1")

### 3. Chain Queries
```
You: Top 5 customers by spending
[Results shown]
You: Now show all their orders
AI: Remembers context and provides relevant query
```

### 4. Review PDFs
- Check results before saving
- PDF includes query, timestamp, and row count
- Share PDFs with stakeholders

## 🚀 Advanced Usage

### Programmatic Access

```python
# In your own Python script
from LLM_CI.database_tools import execute_database_query
import json

query = "SELECT * FROM customers WHERE country = 'USA'"
result_json = execute_database_query.invoke({"sql_query": query})
results = json.loads(result_json)

if results.get('success'):
    for row in results['results']:
        print(row)
```

### Custom Queries via CLI

```bash
python LLM_CI/cli.py --prompt "What's the total revenue by region?"
```

### Batch Processing

Create multiple queries and have the agent process them:
```
You: First, show me active customers. Then show me their total spending.
AI: Executes both queries in sequence
```

## 📚 Next Steps

1. **Try the sample**: Run `python quick_start_database.py`
2. **Read the guide**: Open `DATABASE_FEATURE_GUIDE.md`
3. **Configure your DB**: Edit `db_config.json`
4. **Start asking questions**: Use Chat.py or ChatGUI.py
5. **Generate reports**: Export results to PDF

## ✨ Key Capabilities

✅ Natural language database queries
✅ Automatic SQL generation
✅ User approval before execution
✅ SQL injection prevention
✅ Multiple database support (SQLite, PostgreSQL, MySQL)
✅ Beautiful PDF export with formatting
✅ Automatic PDF viewer integration
✅ ASCII table display
✅ Query result metadata (timestamp, row count)
✅ Complex query support (JOINs, aggregations, filtering)

## 📞 Support

- **User Guide**: See `DATABASE_FEATURE_GUIDE.md`
- **Technical Details**: See `DATABASE_IMPLEMENTATION_SUMMARY.md`
- **Setup Help**: Run `python quick_start_database.py`
- **Configuration**: See `LLM_CI/db_config_examples.py`

---

**Your AI assistant now has the power to answer business questions directly from your database! 🎉**
