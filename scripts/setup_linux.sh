#!/usr/bin/env bash
# ==============================================================================
# Linux System Debugging Tool - Setup Script for Ubuntu / Debian / WSL
# ==============================================================================
set -euo pipefail

echo "================================================================="
echo " Linux System Debugging Tool - Environment Setup"
echo "================================================================="

# 1. Install toolchain packages if apt is available and permissions permit
PKGS=(build-essential gcc gdb make strace clang valgrind python3 python3-pip python3-venv nodejs npm)
echo "[*] Checking required Linux toolchain packages..."

if command -v apt-get >/dev/null 2>&1; then
    if [ "$(id -u)" -eq 0 ]; then
        apt-get update -y
        apt-get install -y "${PKGS[@]}"
    elif sudo -n true >/dev/null 2>&1; then
        sudo apt-get update -y
        sudo apt-get install -y "${PKGS[@]}"
    else
        echo "[!] Non-root user without passwordless sudo. Verifying existing binaries:"
        for pkg in gcc gdb make strace python3; do
            if command -v "$pkg" >/dev/null 2>&1; then
                echo "    - $pkg: available ($(command -v "$pkg"))"
            else
                echo "    - $pkg: NOT FOUND (please install via 'sudo apt install $pkg')"
            fi
        done
    fi
fi

# 2. Build Native C Layer
echo
echo "[*] Compiling Native C Layer (process_launcher, process_status, signal_handler)..."
make -C native clean
make -C native

# 3. Setup Python Backend Dependencies
echo
echo "[*] Installing Python backend dependencies..."
python3 -m pip install --upgrade pip 2>/dev/null || true
python3 -m pip install -r backend/requirements.txt --break-system-packages 2>/dev/null || python3 -m pip install -r backend/requirements.txt

# 4. Build Frontend Assets
echo
echo "[*] Building React + TypeScript + Monaco Frontend..."
if command -v npm >/dev/null 2>&1; then
    (cd frontend && npm install && npm run build)
fi

echo
echo "================================================================="
echo " Setup Complete! You can now start the application:"
echo "   ./run.sh"
echo "================================================================="
