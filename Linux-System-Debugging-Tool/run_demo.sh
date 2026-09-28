#!/usr/bin/env bash
set -e
make
make tests
echo
echo "=== NORMAL TEST ==="
./debugger ./tests/normal_test
echo
echo "=== FILE ERROR TEST ==="
./debugger ./tests/file_error
echo
echo "=== INVALID FD TEST ==="
./debugger ./tests/invalid_fd
echo
echo "=== ABNORMAL EXIT TEST ==="
./debugger ./tests/abnormal_exit
echo
echo "=== SEGMENTATION FAULT TEST ==="
./debugger ./tests/segmentation_fault
