from __future__ import annotations

import json

import pytest
import subprocess
import sys

from tests.test_codex_workcell_memory_candidate_verifier import _bundle

pytestmark = pytest.mark.no_legacy_skip

SCRIPT = "scripts/verify_codex_workcell_memory_candidate_bundle.py"


def test_invalid_candidate_bundle_json_exits_2(tmp_path) -> None:
    bad = tmp_path / "bad.json"; bad.write_text("{", encoding="utf-8")
    result = subprocess.run([sys.executable, SCRIPT, "--candidate-bundle-json", str(bad), "--output", str(tmp_path / "out.json")], text=True, capture_output=True)
    assert result.returncode == 2


def test_missing_candidate_bundle_path_exits_2(tmp_path) -> None:
    result = subprocess.run([sys.executable, SCRIPT, "--candidate-bundle-json", str(tmp_path / "missing.json"), "--output", str(tmp_path / "out.json")], text=True, capture_output=True)
    assert result.returncode == 2


def test_non_object_candidate_bundle_json_exits_2(tmp_path) -> None:
    bad = tmp_path / "bad.json"; bad.write_text("[]", encoding="utf-8")
    result = subprocess.run([sys.executable, SCRIPT, "--candidate-bundle-json", str(bad), "--output", str(tmp_path / "out.json")], text=True, capture_output=True)
    assert result.returncode == 2


def test_invalid_memory_contract_json_exits_2(tmp_path) -> None:
    bundle = tmp_path / "bundle.json"; bundle.write_text(json.dumps(_bundle()), encoding="utf-8")
    bad = tmp_path / "bad_contract.json"; bad.write_text("{", encoding="utf-8")
    result = subprocess.run([sys.executable, SCRIPT, "--candidate-bundle-json", str(bundle), "--memory-contract-json", str(bad), "--output", str(tmp_path / "out.json")], text=True, capture_output=True)
    assert result.returncode == 2


def test_cli_writes_json_summary_and_markdown(tmp_path) -> None:
    bundle = tmp_path / "bundle.json"; bundle.write_text(json.dumps(_bundle(), sort_keys=True), encoding="utf-8")
    out = tmp_path / "out.json"; md = tmp_path / "out.md"
    result = subprocess.run([sys.executable, SCRIPT, "--candidate-bundle-json", str(bundle), "--output", str(out), "--markdown-output", str(md), "--summary"], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    summary = json.loads(result.stdout)
    assert report["verification_status"] == "memory_candidate_bundle_verified"
    assert summary["verifier_only"] is True
    assert md.read_text(encoding="utf-8").startswith("# Codex Workcell Memory Candidate Verifier")


def test_cli_output_is_deterministic(tmp_path) -> None:
    bundle = tmp_path / "bundle.json"; bundle.write_text(json.dumps(_bundle(), sort_keys=True), encoding="utf-8")
    out1 = tmp_path / "out1.json"; out2 = tmp_path / "out2.json"
    for out in (out1, out2):
        result = subprocess.run([sys.executable, SCRIPT, "--candidate-bundle-json", str(bundle), "--output", str(out)], text=True, capture_output=True)
        assert result.returncode == 0
    assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")
