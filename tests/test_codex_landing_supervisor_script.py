from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone


def _matrix_payload(required_failure_count: int = 0) -> str:
    return json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "required_failure_count": required_failure_count, "required_failures": ["mypy_baseline"] if required_failure_count else []})


def test_cli_accepts_inline_matrix_json() -> None:
    proc = subprocess.run([sys.executable, "scripts/codex_landing_supervisor.py", "evaluate", "--title", "[codex:x] ok", "--intended-commit-title", "[codex:x] ok", "--matrix-json", _matrix_payload(), "--summary"], check=False, capture_output=True, text=True)
    assert proc.returncode == 1


def test_cli_exits_nonzero_for_failed_matrix() -> None:
    proc = subprocess.run([sys.executable, "scripts/codex_landing_supervisor.py", "evaluate", "--title", "[codex:x] ok", "--intended-commit-title", "[codex:x] ok", "--matrix-json", _matrix_payload(1)], check=False, capture_output=True, text=True)
    assert proc.returncode == 1
