#!/usr/bin/env bash
# ==============================================================================
# Linux System Debugging Tool - Setup
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

chmod +x scripts/*.sh run.sh 2>/dev/null || true
./scripts/setup_linux.sh
