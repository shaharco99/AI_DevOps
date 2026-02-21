# Environment Setup Guide

## Problem: "LangChain not found" / "Ollama not found" errors

If you're getting errors like:
```
❌ LangChain not available
❌ langchain_ollama not available  
Python executable: /usr/bin/python3
```

**The packages ARE installed, but you're using the WRONG Python!**

## Quick Fix (Recommended)

### Option 1: Use the automatic launcher (Easiest)

```bash
# Run using the Python launcher wrapper
python3 start.py --gui
python3 start.py --prompt "your question"
```

### Option 2: Activate virtual environment manually

```bash
# Activate the virtual environment
source venv/bin/activate

# Now all Python commands will use the correct environment
python unified_interface.py --gui
python unified_agent.py
```

## Understanding the Problem

1. **System Python** (`/usr/bin/python3`):
   - Does NOT have LangChain or Ollama installed
   - This is what runs when you type `python3` normally

2. **Virtual Environment Python** (`./venv/bin/python3`):
   - HAS all required packages installed
   - Must be activated or explicitly used

## Setup (First Time)

If you need to set up the environment from scratch:

```bash
# 1. Create virtual environment
python3 -m venv venv

# 2. Activate it
source venv/bin/activate

# 3. Install requirements
pip install -r requirements/dev.txt

# 4. Now run the application
python unified_interface.py --gui
```

## Verify Installation

### Check which Python is being used:
```bash
which python3
# Shows: /usr/bin/python3 (WRONG) or ./venv/bin/python3 (CORRECT)
```

### Check if packages are installed:
```bash
python3 -c "import langchain; print('✓ LangChain found')"
python3 -c "import langchain_ollama; print('✓ Ollama found')"
```

### Check packages in venv:
```bash
source venv/bin/activate
python3 -m pip list | grep langchain
python3 -m pip list | grep ollama
```

## Common Issues

### "venv: command not found"
Install Python venv module:
```bash
sudo apt-get install python3-venv
```

### "ModuleNotFoundError: No module named 'langchain'"
You're not using the virtual environment:
```bash
source venv/bin/activate
# OR
./start.py
```

### "torch not installed" (optional)
Skip this if you don't need GPU support:
```bash
pip install -r requirements/base.txt --no-deps
pip install langchain langchain-ollama ollama chromadb
```

## Environment Variables

Create a `.env` file in the project root:
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

# Logging
LOG_LEVEL=INFO
```

## Why This Matters

Python virtual environments isolate project dependencies. When you're in a venv:
- Each project has its own packages
- Packages don't interfere with system Python
- Easy to manage different versions

```
System Python              Virtual Environment
├─ sys.path                ├─ venv/bin/python3
├─ installed packages      ├─ venv/lib/python3.x/site-packages/
│  └─ Missing: langchain   │  ├─ ✓ langchain
│  └─ Missing: ollama      │  ├─ ✓ ollama
│                          │  └─ (all requirements)
```

## Getting Help

If you still have issues:

1. Show what Python you're using:
   ```bash
   which python3
   python3 --version
   ```

2. Check installed packages:
   ```bash
   source venv/bin/activate
   python3 -m pip list
   ```

3. Test imports:
   ```bash
   source venv/bin/activate
   python3 -c "
   try:
       import langchain
       print('✓ langchain OK')
   except ImportError as e:
       print(f'✗ langchain: {e}')
   try:
       import langchain_ollama
       print('✓ langchain_ollama OK')
   except ImportError as e:
       print(f'✗ langchain_ollama: {e}')
   "
   ```
