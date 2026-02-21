#!/usr/bin/env python3
"""
Environment Diagnostic Script

Checks:
- Virtual environment status
- Required packages
- Python version
- Database configuration
- LLM provider settings
"""

import os
import sys
import subprocess
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_, **__):
        pass

# Load environment variables from .env file
load_dotenv()

def print_section(title):
    """Print a formatted section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def check_python_executable():
    """Check Python executable and version."""
    print_section("Python Environment")
    print(f"Executable: {sys.executable}")
    print(f"Version: {sys.version}")
    
    # Check if in venv
    in_venv = sys.prefix != sys.base_prefix
    print(f"Virtual Environment: {'✓ YES' if in_venv else '✗ NO'}")
    
    if in_venv:
        print(f"Venv Path: {sys.prefix}")
    else:
        print("⚠️  NOT using virtual environment!")
    
    return in_venv

def check_packages():
    """Check if required packages are installed."""
    print_section("Required Packages")
    
    # Map (import_name, pip_name, description)
    required = {
        'langchain': ('langchain', 'LangChain core'),
        'langchain_ollama': ('langchain_ollama', 'Ollama integration'),
        'langchain_core': ('langchain_core', 'LangChain core types'),
        'chromadb': ('chromadb', 'Vector database'),
        'sqlalchemy': ('sqlalchemy', 'SQL toolkit'),
        'langchain_community': ('langchain_community', 'LangChain community'),
    }
    
    all_ok = True
    for import_name, description in required.items():
        try:
            module = __import__(import_name)
            version = getattr(module, '__version__', 'unknown')
            print(f"✓ {import_name:25} ({version:10}) - {description}")
        except ImportError as e:
            print(f"✗ {import_name:25} (MISSING)      - {description}")
            all_ok = False
    
    return all_ok

def check_database_config():
    """Check database configuration."""
    print_section("Database Configuration")
    
    db_config_file = os.getenv('DB_CONFIG_FILE', 'db_config.json')
    print(f"Config File: {db_config_file}")
    
    config_path = Path(db_config_file)
    if config_path.exists():
        print(f"✓ Config file exists")
        try:
            import json
            with open(config_path) as f:
                config = json.load(f)
            print(f"  Type: {config.get('type', 'unknown')}")
            if config.get('type') == 'sqlite':
                db_path = config.get('database')
                db_exists = Path(db_path).exists()
                status = "✓" if db_exists else "✗"
                print(f"  {status} Database: {db_path}")
        except Exception as e:
            print(f"✗ Error reading config: {e}")
    else:
        print(f"✗ Config file NOT found: {config_path}")

def check_environment_variables():
    """Check important environment variables."""
    print_section("Environment Variables")
    
    important_vars = [
        'LLM_PROVIDER',
        'OLLAMA_BASE_URL',
        'OLLAMA_MODEL',
        'DB_CONFIG_FILE',
        'LOG_LEVEL',
    ]
    
    for var in important_vars:
        value = os.getenv(var)
        if value:
            print(f"✓ {var:20} = {value}")
        else:
            print(f"  {var:20} = (not set)")

def check_venv_directory():
    """Check virtual environment directory."""
    print_section("Virtual Environment Status")
    
    script_dir = Path(__file__).parent
    venv_path = script_dir / "venv"
    python_exe = venv_path / "bin" / "python3"
    
    print(f"Venv path: {venv_path}")
    print(f"Exists: {'✓ YES' if venv_path.exists() else '✗ NO'}")
    
    if venv_path.exists():
        print(f"Python exe: {python_exe}")
        print(f"Exists: {'✓ YES' if python_exe.exists() else '✗ NO'}")

def main():
    """Run all diagnostics."""
    print("\n" + "="*60)
    print("  MCP Environment Diagnostics")
    print("="*60)
    
    in_venv = check_python_executable()
    pkgs_ok = check_packages()
    check_database_config()
    check_environment_variables()
    check_venv_directory()
    
    print_section("Summary")
    
    if in_venv and pkgs_ok:
        print("✓ Environment looks good!")
        print("\nYou can now run:")
        print("  python unified_interface.py --gui")
        print("  python unified_interface.py --prompt 'your question'")
    else:
        print("⚠️  There are issues with your environment:")
        if not in_venv:
            print("\n1. You're not using the virtual environment!")
            print("   Solution: source venv/bin/activate")
        if not pkgs_ok:
            print("\n2. Some packages are missing!")
            print("   Solution: pip install -r requirements/dev.txt")
        print("\n3. Or use the launcher script:")
        print("   python3 start.py --gui")
    
    print("\nFor more details, see: SETUP.md")
    print()

if __name__ == "__main__":
    main()
