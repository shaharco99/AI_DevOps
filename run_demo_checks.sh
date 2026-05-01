#!/bin/bash
# Demo Checks Runner - Wrapper script for demo_checks.py
# This script ensures the demo environment is set up and runs all checks

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting AI DevOps Assistant Demo Checks..."
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

# Check if in virtual environment or activate it
if [[ -z "${VIRTUAL_ENV}" ]]; then
    if [[ -f "$SCRIPT_DIR/venv/bin/activate" ]]; then
        echo "Activating virtual environment..."
        source "$SCRIPT_DIR/venv/bin/activate"
    else
        echo "Warning: Virtual environment not found. Attempting to use system Python."
    fi
fi

PYTHON="$(command -v python3 || command -v python)"
PIP="$(command -v pip || command -v pip3)"
if [[ -n "${VIRTUAL_ENV}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
    PYTHON="${VIRTUAL_ENV}/bin/python"
    PIP="${VIRTUAL_ENV}/bin/pip"
fi

# Install requests if needed (for API checks)
"$PYTHON" -c "import requests" 2>/dev/null || {
    echo "Installing requests package..."
    "$PIP" install requests > /dev/null
}

# Run the demo checks
cd "$SCRIPT_DIR"
python3 demo_checks.py "$@"
exit $?
