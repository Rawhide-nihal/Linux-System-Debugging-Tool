#!/usr/bin/env bash
set -euo pipefail
make
make tests
./ldst
