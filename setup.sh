#!/usr/bin/env bash
set -euo pipefail

echo "================================================"
echo " LDST — Linux System Debugging Tool Setup"
echo "================================================"
echo

# Check and install missing Linux packages if apt-get and non-interactive or interactive sudo is requested
MISSING_PKGS=()
command -v gcc >/dev/null 2>&1 || MISSING_PKGS+=("build-essential")
command -v make >/dev/null 2>&1 || MISSING_PKGS+=("build-essential")
command -v strace >/dev/null 2>&1 || MISSING_PKGS+=("strace")
command -v gdb >/dev/null 2>&1 || MISSING_PKGS+=("gdb")
command -v python3 >/dev/null 2>&1 || MISSING_PKGS+=("python3")

if ! python3 -c "import flask" >/dev/null 2>&1; then
    MISSING_PKGS+=("python3-flask")
fi

if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    echo "[Setup] Checking system packages: ${MISSING_PKGS[*]}"
    if command -v apt-get >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
        sudo apt-get update
        sudo apt-get install -y build-essential strace gdb python3 python3-flask python3-venv
    else
        echo "[Note] Some optional system packages (${MISSING_PKGS[*]}) are not installed globally."
        echo "       If needed on Ubuntu, install with:"
        echo "         sudo apt update && sudo apt install -y build-essential strace gdb python3 python3-flask python3-venv"
    fi
fi

# Create required project directories
mkdir -p logs traces reports results tests web/static/images

# Optional Python virtual environment setup if venv + pip are available
if ! python3 -c "import flask" >/dev/null 2>&1; then
    if [ ! -d ".venv" ] && python3 -m venv .venv >/dev/null 2>&1; then
        if [ -x ".venv/bin/pip" ]; then
            .venv/bin/pip install --quiet flask || true
        fi
    fi
fi

echo
echo "[Setup] Building LDST C Debugging Core and Official Test Suite..."
make clean
make
make tests

chmod +x setup.sh run.sh selftest.sh 2>/dev/null || true

echo
echo "================================================"
echo " LDST Setup Complete!"
echo "------------------------------------------------"
echo " Run Self-Tests : ./selftest.sh"
echo " Start CLI Tool : ./ldst"
echo " Start Web GUI  : ./run.sh"
echo "================================================"
