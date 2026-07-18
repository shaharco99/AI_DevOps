# MCP Project - Setup & Troubleshooting Guide

## Quick Start

### The Problem
You're seeing errors like:
```
LangChain not available
langchain_ollama not available
Python executable: /usr/bin/python3
```

**But the packages ARE installed!** They're just in the virtual environment, not system Python.

### The Solution

Use the **automatic launcher** (recommended):
```bash
python3 start.py --gui
```

Or manually activate the virtual environment:
```bash
source venv/bin/activate
python unified_interface.py --gui
```

## Available Tools

### 1. Launcher Script (Recommended)
**File:** `start.py`

Automatically uses the correct Python environment:
```bash
python3 start.py --gui
python3 start.py --prompt "show me all clients"
python3 start.py --rag --query "your question"
```


### 2. Diagnostic Tool
Check your environment:
```bash
python3 start.py  # (this runs the diagnostic automatically)
# Or manually:
/home/shahar/repos/MCP/venv/bin/python3 diagnose.py
```

### 3. Manual Virtual Environment
```bash
source venv/bin/activate
python unified_interface.py --gui
```

## Understanding the Issue

### Why This Happens

Python has two separate package locations:

```
System Python (/usr/bin/python3)
├─ Installed packages: (minimal)
├─ Missing: langchain
├─ Missing: ollama
└─ Missing: chromadb

Virtual Environment (./venv)
├─ Installed packages: ✓
├─ ✓ langchain 1.0.3
├─ ✓ ollama 0.6.0
├─ ✓ chromadb
└─ ✓ All dependencies
```

When you run `python3` normally, you get system Python.
When you activate the venv, you get venv Python with all packages.

### How to Tell Which You're Using

```bash
# Check the Python path
which python3

# System: /usr/bin/python3  (❌ WRONG)
# Venv:   /path/to/MCP/venv/bin/python3  (✓ CORRECT)

# Check if in a venv
python3 -c "import sys; print(sys.prefix != sys.base_prefix)"
# True = in venv ✓
# False = not in venv ❌
```

## Installation & First Setup

### Step 1: Create and activate venv
```bash
cd /home/shahar/repos/MCP
python3 -m venv venv
source venv/bin/activate
```

### Step 2: Install packages
```bash
pip install -r requirements/dev.txt
```

### Step 3: Run the application
```bash
python unified_interface.py --gui
# OR use launcher:
python3 start.py --gui
```

## Modes of Operation

### GUI Mode
Interactive graphical interface:
```bash
python3 start.py --gui
```

### CLI Prompt Mode
Direct prompt execution:
```bash
python3 start.py --prompt "show me all clients"
python3 start.py --prompt "what is cloud computing?"
```

### RAG Mode (Retrieval-Augmented Generation)
Agentic RAG with self-reflection:
```bash
python3 start.py --rag --query "your question"
```

### Interactive Chat
Interactive conversation mode:
```bash
python3 start.py --cli
```

## Troubleshooting

### Issue: "No module named 'langchain'"

**Cause:** Using system Python instead of venv

**Fix (Option 1 - Automatic):**
```bash
python3 start.py --gui
```

**Fix (Option 2 - Manual):**
```bash
source venv/bin/activate
python unified_interface.py --gui
```

**Verification:**
```bash
which python3
# Should show: /home/shahar/repos/MCP/venv/bin/python3
```

### Issue: "venv: command not found"

**Cause:** Python venv module not installed

**Fix:**
```bash
# On Ubuntu/Debian
sudo apt-get install python3-venv

# Create venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements/dev.txt
```

### Issue: "ModuleNotFoundError: No module named 'ollama'"

**Cause:** Packages not installed in venv

**Fix:**
```bash
source venv/bin/activate
pip install -r requirements/dev.txt
```

### Issue: "LangChain OllamaLLM not available, using dummy LLM"

This is a fallback message. The agent still works and can:
- ✓ Execute database queries
- ✓ Return results directly
- ❌ Can't use advanced LLM features

To fix:
```bash
python3 start.py --gui  # Uses correct Python automatically
# OR
source venv/bin/activate && python unified_interface.py --gui
```

### Issue: Database errors

Check database configuration:
```bash
# View database config
cat db_config.json

# Run diagnostics
/home/shahar/repos/MCP/venv/bin/python3 diagnose.py

# Check for database file
ls -lah sample_database.db
```

## Environment Variables

Create `.env` file in project root:
```env
# LLM Configuration
LLM_PROVIDER=OLLAMA
OLLAMA_MODEL=llama3.1:8b
OLLAMA_BASE_URL=http://localhost:11434

# Database
DB_CONFIG_FILE=db_config.json

# RAG Settings
RAG_COLLECTION_NAME=rag_collection
RAG_DOCS_DIR=LLM_CI/docs
VAULT_FILE=LLM_CI/vault.txt

# Logging
LOG_LEVEL=INFO
```

## Requirements Management

### Different requirement sets:
- **dev.txt** - Development (includes testing tools)
- **prod.txt** - Production (minimal dependencies)
- **base.txt** - Base packages for all environments

### Install all requirements:
```bash
source venv/bin/activate
pip install -r requirements/dev.txt
```

### Update requirements:
```bash
pip freeze > requirements/current.txt
```

## Helpful Commands

### Check Python version
```bash
python3 --version
```

### List installed packages
```bash
source venv/bin/activate
python3 -m pip list
```

### Check specific package
```bash
source venv/bin/activate
python3 -c "import langchain; print(langchain.__version__)"
```

### Test imports
```bash
source venv/bin/activate
python3 << 'EOF'
try:
    import langchain
    print("✓ langchain")
except ImportError as e:
    print(f"✗ langchain: {e}")
    
try:
    import langchain_ollama
    print("✓ langchain_ollama")
except ImportError as e:
    print(f"✗ langchain_ollama: {e}")
EOF
```

### Run diagnostics
```bash
source venv/bin/activate
python3 diagnose.py
```

## Getting Help

If you're still having issues:

1. **Run diagnostics:**
   ```bash
   python3 start.py  # Shows configuration
   # or
   /home/shahar/repos/MCP/venv/bin/python3 diagnose.py
   ```

2. **Check Python location:**
   ```bash
   which python3
   ```

3. **Verify venv:**
   ```bash
   source venv/bin/activate
   which python3  # Should show venv path
   ```

4. **Check packages:**
   ```bash
   source venv/bin/activate
   python3 -m pip list | grep langchain
   ```

## File Locations

- **Launcher:** `start.py`
- **Diagnostics:** `diagnose.py`
- **Setup guide:** `SETUP.md`
- **Main app:** `unified_interface.py`
- **Database:** `sample_database.db`
- **Config:** `db_config.json`
- **Database tools:** `LLM_CI/database_tools.py`
- **Virtual environment:** `venv/` (hidden from git)

## Key Files

| File | Purpose |
|------|---------|
| `start.py` | Python launcher (recommended) |
| `diagnose.py` | Environment diagnostics |
| `unified_interface.py` | Main application |
| `unified_agent.py` | Agent logic |
| `LLM_CI/database_tools.py` | Database query execution |
| `LLM_CI/Utils.py` | LLM provider setup |
| `requirements/dev.txt` | Development dependencies |
| `.env` | Environment variables (create manually) |

## Summary

- **Always use one of these methods to run the app:**
  1. `python3 start.py` (automatic & recommended)
  2. `source venv/bin/activate && python unified_interface.py`

- **Never use:** `python unified_interface.py` directly (uses system Python)

- **Check environment anytime with:** `python3 start.py` (shows config)

---

**Last updated:** 2026-02-21

For more detailed setup information, see `SETUP.md`
