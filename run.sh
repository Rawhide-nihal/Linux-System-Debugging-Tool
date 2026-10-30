#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

HOST="${LDST_HOST:-127.0.0.1}"
PORT="${LDST_PORT:-5000}"

echo "================================================"
echo " LDST — Linux System Debugging Tool"
echo "================================================"
echo
echo "Checking environment..."

if [ ! -d "/proc" ]; then
    echo "[ERROR] Linux /proc filesystem not detected. LDST requires Ubuntu/Linux."
    exit 1
fi

if command -v gcc >/dev/null 2>&1; then
    echo "GCC ............. OK"
else
    echo "GCC ............. MISSING (Install: sudo apt install build-essential)"
fi

if command -v strace >/dev/null 2>&1; then
    echo "strace .......... OK"
else
    echo "strace .......... MISSING (Install: sudo apt install strace)"
fi

if command -v gdb >/dev/null 2>&1; then
    echo "GDB ............. OK"
else
    echo "GDB ............. MISSING (Install: sudo apt install gdb)"
fi

# Ensure runtime directories exist
mkdir -p logs traces reports results tests web/static/images

# Build C core and built-in test binaries if missing
if [ ! -x "./debugger" ] || [ ! -x "./autodebug" ] || [ ! -x "./ldst" ] || [ ! -x "./tests/normal_test" ]; then
    make >/dev/null
    make tests >/dev/null
fi

if [ -x "./debugger" ] && [ -x "./autodebug" ] && [ -x "./ldst" ]; then
    echo "LDST Core ....... OK"
else
    echo "LDST Core ....... FAILED"
    exit 1
fi

PYTHON_BIN="python3"
if [ -x ".venv/bin/python3" ] && .venv/bin/python3 -c "import flask" >/dev/null 2>&1; then
    PYTHON_BIN=".venv/bin/python3"
fi

if command -v "$PYTHON_BIN" >/dev/null 2>&1 && [ -f "web/app.py" ]; then
    echo "Web Backend ..... OK"
else
    echo "Web Backend ..... FAILED (python3 or web/app.py missing)"
    exit 1
fi

echo
echo "LDST Web Interface is running:"
echo
echo "http://${HOST}:${PORT}"
echo
echo "Press Ctrl+C to stop."
echo "================================================"

exec "$PYTHON_BIN" web/app.py
