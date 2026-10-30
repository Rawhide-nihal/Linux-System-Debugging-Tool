#!/usr/bin/env bash
# ==============================================================================
# Linux System Debugging Tool - Launch Script
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

# Ensure native layer is built
if [ ! -f "native/libldstnative.so" ]; then
    echo "[*] Building native Linux libraries..."
    make -C native
fi

# Ensure frontend is built if dist does not exist
if [ ! -d "frontend/dist" ]; then
    echo "[*] Building frontend assets..."
    (cd frontend && npm install && npm run build)
fi

echo "================================================================="
echo " Starting Linux System Debugging Tool Workbench"
echo " Access URL: http://127.0.0.1:8000"
echo "================================================================="

exec python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
