#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -f "$ROOT_DIR/requirements-dev.txt" ]; then
    python3 -m pip install -r "$ROOT_DIR/requirements-dev.txt"
else
    python3 -m pip install pyyaml pytest mypy pre-commit
fi
