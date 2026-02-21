#!/usr/bin/env python3
"""
Launcher script - Ensures the correct Python environment is used

This script:
1. Checks if the virtual environment exists
2. Verifies required packages are installed
3. Provides helpful error messages if something is wrong
4. Runs the unified_interface with the correct environment
"""

import os
import sys
import subprocess
from pathlib import Path

def check_venv():
    """Check if virtual environment exists and is valid."""
    script_dir = Path(__file__).parent.resolve()
    
    # Try .venv first, then venv
    venv_path = script_dir / ".venv"
    if not venv_path.exists():
        venv_path = script_dir / "venv"
    
    python_exe = venv_path / "bin" / "python3"
    
    if not venv_path.exists():
        print("❌ ERROR: Virtual environment not found!", file=sys.stderr)
        print(f"   Expected location: {venv_path}", file=sys.stderr)
        print("\n🔧 Solution:", file=sys.stderr)
        print("   Create the virtual environment with:", file=sys.stderr)
        print("   $ python3 -m venv venv", file=sys.stderr)
        print("   $ pip install -r requirements.txt", file=sys.stderr)
        return None, None
    
    if not python_exe.exists():
        print("❌ ERROR: Python executable not found in venv!", file=sys.stderr)
        print(f"   Expected: {python_exe}", file=sys.stderr)
        print("   Virtual environment may be corrupted", file=sys.stderr)
        return None, None
    
    return venv_path, python_exe


def check_packages(python_exe):
    """Check if required packages are installed."""
    required = ['langchain', 'langchain-ollama']
    
    try:
        result = subprocess.run(
            [str(python_exe), '-m', 'pip', 'list'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        installed = result.stdout.lower()
        missing = [pkg for pkg in required if pkg not in installed]
        
        if missing:
            print(f"❌ ERROR: Missing packages: {', '.join(missing)}", file=sys.stderr)
            print("\n🔧 Solution:", file=sys.stderr)
            print("   Install requirements with:", file=sys.stderr)
            print("   $ pip install -r requirements.txt", file=sys.stderr)
            return False
        
        return True
    except Exception as e:
        print(f"⚠️  Warning: Could not verify packages: {e}", file=sys.stderr)
        return True  # Continue anyway


def main():
    """Check environment and launch the interface."""
    venv_path, python_exe = check_venv()
    
    if not python_exe:
        sys.exit(1)
    
    # Show environment info
    print(f"✓ Using Python: {python_exe}", file=sys.stderr)
    
    if not check_packages(python_exe):
        sys.exit(1)
    
    # Get the script directory
    script_dir = Path(__file__).parent.resolve()
    interface_script = script_dir / "unified_interface.py"
    
    print("✓ Starting unified interface...\n", file=sys.stderr)
    
    # Run the interface with all arguments passed through
    result = subprocess.run(
        [str(python_exe), str(interface_script)] + sys.argv[1:],
        cwd=str(script_dir)
    )
    
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
