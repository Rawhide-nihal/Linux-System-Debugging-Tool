#!/usr/bin/env bash
set -e
echo "Installing required Ubuntu packages..."
sudo apt update
sudo apt install -y build-essential strace gdb tree
echo "Building project..."
make
make tests
echo "Setup complete."
