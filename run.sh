#!/usr/bin/env bash
# ==============================================================================
# Linux System Debugging Tool - Main Launcher
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f "native/libldstnative.so" ]; then
    echo "[*] Compiling native layer..."
    make -C native
fi

if [ ! -d "frontend/dist" ]; then
    echo "[*] Compiling frontend bundle..."
    (cd frontend && npm install && npm run build)
fi

echo "================================================================="
echo " Linux System Debugging Tool 3.0"
echo " Listening on http://127.0.0.1:8000"
echo "================================================================="

exec python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
