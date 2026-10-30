#!/usr/bin/env bash
# ==============================================================================
# Linux System Debugging Tool - Development Mode
# Runs FastAPI backend and Vite frontend with hot-reloading.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

echo "[*] Launching FastAPI backend on http://127.0.0.1:8000..."
python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!

cleanup() {
    echo "Stopping servers..."
    kill "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[*] Launching Vite development server..."
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
