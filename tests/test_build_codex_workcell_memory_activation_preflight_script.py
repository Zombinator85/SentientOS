from __future__ import annotations

import json
import subprocess
import sys

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_memory_contract import build_codex_workcell_memory_contract
from sentientos.codex_workcell_memory_candidate_verifier import verify_codex_workcell_memory_candidate_bundle
from tests.test_codex_workcell_memory_candidate_verifier import _add_glow, _add_ledger, _bundle, _summary

SCRIPT = "scripts/build_codex_workcell_memory_activation_preflight.py"


def _write(path, data: dict) -> None:
    path.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")


def _fixtures(tmp_path):
    contract = build_codex_workcell_memory_contract()
    bundle = _add_glow(_add_ledger(_bundle()))
    verifier = verify_codex_workcell_memory_candidate_bundle(bundle, _summary(bundle), contract, {"provided": True, "path": "contract.json", "digest": "d", "byte_size": 1, "readable_json": True, "error": None})
    paths = []
    for name, data in (("contract", contract), ("bundle", bundle), ("verifier", verifier)):
        path = tmp_path / f"{name}.json"
        _write(path, data)
        paths.append(path)
    return paths


def test_cli_writes_json_markdown_and_summary(tmp_path) -> None:
    contract, bundle, verifier = _fixtures(tmp_path)
    output = tmp_path / "preflight.json"
    markdown = tmp_path / "preflight.md"
    result = subprocess.run([sys.executable, SCRIPT, "--memory-contract-json", str(contract), "--candidate-bundle-json", str(bundle), "--candidate-verifier-json", str(verifier), "--output", str(output), "--markdown-output", str(markdown), "--summary"], check=False, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["activation_preflight_status"] == "activation_prerequisites_satisfied_for_future_design"
    assert "activation_preflight_status" in result.stdout
    assert markdown.read_text(encoding="utf-8").startswith("# Codex Workcell Memory Activation Preflight")


@pytest.mark.parametrize("content", ["{", "[]"])
def test_cli_invalid_or_non_object_json_exits_2(tmp_path, content: str) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(content, encoding="utf-8")
    result = subprocess.run([sys.executable, SCRIPT, "--memory-contract-json", str(bad), "--output", str(tmp_path / "out.json")], check=False, text=True, capture_output=True)
    assert result.returncode == 2
    assert "codex_workcell_memory_activation_preflight_error" in result.stderr


def test_cli_missing_input_path_exits_2(tmp_path) -> None:
    result = subprocess.run([sys.executable, SCRIPT, "--candidate-verifier-json", str(tmp_path / "missing.json"), "--output", str(tmp_path / "out.json")], check=False, text=True, capture_output=True)
    assert result.returncode == 2
