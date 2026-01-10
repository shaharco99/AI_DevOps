# Database Feature - Quick Reference Card

## 🚀 Quick Start Commands

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Setup sample database
python quick_start_database.py

# 3. Run chat interface
cd LLM_CI
python Chat.py

# 4. Try a query
You: Show me all customers from the USA
```

## 📁 Key Files

| File | Location | Purpose |
|------|----------|---------|
| Setup Guide | `GETTING_STARTED_DATABASE.md` | Start here for 5-min setup |
| User Guide | `DATABASE_FEATURE_GUIDE.md` | Complete usage documentation |
| Tech Details | `DATABASE_IMPLEMENTATION_SUMMARY.md` | Architecture & API reference |
| Quick Setup | `quick_start_database.py` | Automated sample DB creation |
| Config Template | `LLM_CI/db_config.template.json` | Database configuration |
| Core Code | `LLM_CI/database_tools.py` | Database functionality |
| PDF Export | `LLM_CI/pdf_generator.py` | PDF generation |
| Workflow | `LLM_CI/query_confirmation.py` | Query approval & export |

## ⚙️ Configuration

### SQLite (Default)
```json
{
  "type": "sqlite",
  "database": "database.db"
}
```

### PostgreSQL
```json
{
  "type": "postgresql",
  "host": "localhost",
  "port": 5432,
  "user": "postgres",
  "password": "password",
  "database": "dbname"
}
```

### MySQL
```json
{
  "type": "mysql",
  "host": "localhost",
  "port": 3306,
  "user": "root",
  "password": "password",
  "database": "dbname"
}
```

### MSSQL (SQL Server)
```json
{
  "type": "mssql",
  "host": "localhost",
  "port": 1433,
  "user": "sa",
  "password": "password",
  "database": "dbname",
  "driver": "ODBC Driver 17 for SQL Server"
}
```

Save as `LLM_CI/db_config.json`

## 💬 Example Queries to Try

```
# Simple selection
"Show me all active customers"
"List orders from July 2023"

# Aggregations
"How many orders did each customer place?"
"What's the total revenue by country?"

# Filtering & sorting
"Show me orders over $500, sorted by amount"
"Top 5 products by sales volume"

# Complex queries
"Show me customers who spent more than $1000"
"List employees hired in 2024 by department"
"Which products are low on inventory?"
```

## ✨ Workflow

1. **Ask Question** → "Show me customers from USA"
2. **Review SQL** → `SELECT * FROM customers WHERE country = 'USA'`
3. **Approve** → Type `yes`
4. **View Results** → Table displayed in terminal
5. **Export PDF** → Choose `yes` to save PDF

## 🛡️ Safety

### Blocked Operations
- ❌ DROP
- ❌ TRUNCATE
- ❌ DELETE
- ❌ ALTER
- ❌ CREATE

### Allowed Operations
- ✅ SELECT
- ✅ Complex queries with JOINs
- ✅ Aggregations (GROUP BY, COUNT, etc.)
- ✅ Filtering and sorting

## 📊 Database Information

**Supported Databases**:
- SQLite (default, file-based)
- PostgreSQL (enterprise)
- MySQL (scalable)
- MSSQL/SQL Server (Windows-native)

**Sample Database Tables** (from quick_start_database.py):
- `customers` - id, name, email, country, created_date, is_active
- `orders` - id, customer_id, order_date, total_amount, status
- `products` - id, name, category, price, stock

## 🆘 Troubleshooting

| Problem | Solution |
|---------|----------|
| Connection fails | Check db_config.json, verify server running |
| Table not found | Ask agent: "What tables exist in this database?" |
| Query rejected | Type "no" to ask agent for refined query |
| PDF won't open | Check query_results/ folder, ensure reportlab installed |
| Import errors | Run: `pip install --upgrade -r requirements.txt` |

## 🔗 Integration

The database tools work with existing features:

```python
# In your Chat.py / ChatGUI.py (automatic integration)
User: "Load report.pdf and compare with database sales"
# Uses: doc_loader + execute_database_query
```

## 📦 Dependencies Added

```
reportlab>=3.6.0              # PDF generation
psycopg2-binary>=2.9.0        # PostgreSQL (optional)
mysql-connector-python>=8.0   # MySQL (optional)
pyodbc>=4.0                   # MSSQL/SQL Server (optional)
```

SQLite is built-in to Python - no additional package needed.

## 🎯 Common Tasks

### Generate Sales Report
```
You: Total sales by region for 2024
[AI generates query]
You: yes
[Results shown]
You: yes (for PDF)
✓ PDF saved: query_results/query_results_TIMESTAMP.pdf
```

### Customer Analysis
```
You: Customers who haven't purchased in 90 days
You: yes
[Results displayed]
You: yes (for PDF)
✓ Report ready
```

### Inventory Check
```
You: Products with less than 10 units in stock
You: yes
[Low inventory items shown]
You: yes (for PDF)
✓ Inventory report generated
```

## 🚀 Advanced Usage

### Multiple Databases
Create different config files:
- `db_config.json` - Default config
- `db_config_prod.json` - Production DB
- `db_config_analytics.json` - Analytics DB

Switch by renaming the config file.

### Environment Variables Alternative
Instead of `db_config.json`, set in `.env`:
```
DB_TYPE=postgresql
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=password
DB_NAME=database
```

### Programmatic Access
```python
from database_tools import execute_database_query
import json

result = execute_database_query.invoke({
    "sql_query": "SELECT * FROM customers WHERE country = 'USA'"
})
data = json.loads(result)
for row in data['results']:
    print(row)
```

## 📞 Documentation Links

| Need | Read |
|------|------|
| 5-min setup | GETTING_STARTED_DATABASE.md |
| Complete guide | DATABASE_FEATURE_GUIDE.md |
| Technical info | DATABASE_IMPLEMENTATION_SUMMARY.md |
| Setup help | quick_start_database.py |
| Config examples | LLM_CI/db_config_examples.py |

## ✅ Implementation Status

All features implemented and tested:
- [x] Database connection & query execution
- [x] Multi-database support
- [x] SQL query generation by AI
- [x] Query approval workflow
- [x] PDF export functionality
- [x] Safety & validation
- [x] Error handling
- [x] Documentation complete
- [x] Quick start example
- [x] Configuration templates

## 🎉 Ready to Go!

Your project now has complete database query capabilities integrated into your AI assistant. Start with the quick start guide and you'll be querying databases in minutes!

**Begin here**: `GETTING_STARTED_DATABASE.md`
