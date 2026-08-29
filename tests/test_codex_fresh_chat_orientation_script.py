from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip


def test_fresh_chat_orientation_cli_emits_versioned_json() -> None:
    result = subprocess.run([sys.executable, "scripts/codex_fresh_chat_orientation.py"], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "sentientos.codex_fresh_chat_orientation:v1"
    assert payload["status"] == "orientation_observed"


def test_fresh_chat_orientation_cli_emits_structured_failure(tmp_path: Path) -> None:
    result = subprocess.run([sys.executable, "scripts/codex_fresh_chat_orientation.py", "--repository", str(tmp_path)], check=False, capture_output=True, text=True)
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "orientation_failed"
