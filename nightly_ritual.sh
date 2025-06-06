#!/bin/bash
set -e
export LUMOS_AUTO_APPROVE=1
python privilege_lint.py
python verify_audits.py logs/
pytest -q
mypy --ignore-missing-imports .
echo "Cathedral: blessed and audited."
