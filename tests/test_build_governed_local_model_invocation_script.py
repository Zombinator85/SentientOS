# mypy: ignore-errors
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

SCRIPT = Path("scripts/build_governed_local_model_invocation.py")

def test_cli_build_validate_and_invoke_fixture(tmp_path: Path) -> None:
    model = tmp_path / "m.gguf"; model.write_bytes(b"bytes")
    out = tmp_path / "map.json"
    result = subprocess.run([sys.executable, str(SCRIPT), "build-map", "--model", str(model), "--engine", "llama_cpp", "--allowed-root", str(tmp_path), "--output", str(out), "--summary"], check=True, text=True, capture_output=True)
    assert json.loads(result.stdout)["eligible_count"] == 1
    subprocess.run([sys.executable, str(SCRIPT), "validate-map", str(out)], check=True, text=True, capture_output=True)
    receipt = subprocess.run([sys.executable, str(SCRIPT), "invoke-fixture", "--model", str(model), "--engine", "llama_cpp", "--allowed-root", str(tmp_path), "--prompt", "hello", "--correlation-id", "cli-1", "--runtime-root", str(tmp_path / "runtime"), "--fixture-response", "hi"], check=True, text=True, capture_output=True)
    payload = json.loads(receipt.stdout)
    assert payload["status"] == "admitted_completed"
