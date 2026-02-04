#!/bin/bash
set -e
export LUMOS_AUTO_APPROVE=1
python privilege_lint_cli.py
python verify_audits.py logs/
python -m pip install -e .[dev]
python -m scripts.run_tests -q
mypy --ignore-missing-imports .
echo "Cathedral: blessed and audited."
