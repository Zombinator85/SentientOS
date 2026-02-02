#!/bin/bash

# Batch Setup for Final SentientOS Submission Prep
# -------------------------------------------------
# Applies environment patches, test runs, audit rituals, and doc validations

# Activate environment
source ttsenv/Scripts/activate

# Update pip
python -m pip install --upgrade pip

# Reinstall known missing dependencies
pip install requests playsound TTS==0.14 torch

# Install project dependencies
python -m pip install -e .[dev]

# Run audit linter with bypass flag
echo "\n[+] Running privilege_lint_cli.py with LUMOS_AUTO_APPROVE..."
LUMOS_AUTO_APPROVE=1 python privilege_lint_cli.py

# Run audit verifier
echo "\n[+] Verifying audit chain integrity..."
LUMOS_AUTO_APPROVE=1 python verify_audits.py logs/

# Optional connector health test
echo "\n[+] Running connector health check..."
LUMOS_AUTO_APPROVE=1 python check_connector_health.py || echo "[!] Warning: connector health check skipped or failed."

# Run test suite
echo "\n[+] Running pytest (non-env)..."
pytest -m "not env" -q || echo "[!] Some tests failed. Check logs."

# Run mypy check (summary only)
echo "\n[+] Running mypy..."
mypy --ignore-missing-imports . > mypy_results.txt || echo "[!] Mypy errors detected. See mypy_results.txt"
grep 'error:' mypy_results.txt | tee mypy_summary.txt

# Echo environment guidance
echo "\n[+] Environment variables in use:"
echo "  LUMOS_AUTO_APPROVE=1"
echo "  OPENAI_CONNECTOR_LOG (defaults to logs/openai_connector.jsonl)"
echo "\n[+] Output: logs/, audit/ and audio_logs/ folders will be populated if TTS runs successfully."

# Launch main demo if requested
read -p "Run TTS demo now? [y/N]: " RUN_DEMO
if [[ "$RUN_DEMO" == "y" || "$RUN_DEMO" == "Y" ]]; then
  python main.py
fi

# Git status check
read -p "Check git status before exit? [y/N]: " GIT_STATUS
if [[ "$GIT_STATUS" == "y" || "$GIT_STATUS" == "Y" ]]; then
  git status
fi

echo "\n[✓] Batch complete."
