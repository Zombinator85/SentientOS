from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_storage_policy_contract import build_codex_workcell_storage_policy_contract

SCRIPT = Path("scripts/build_codex_workcell_storage_transaction_plan.py")


def _write(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    return path


def _args(tmp_path: Path) -> tuple[list[str], Path, Path]:
    output = tmp_path / "plan.json"
    markdown = tmp_path / "plan.md"
    files = {
        "storage-policy-contract-json": _write(tmp_path / "policy.json", build_codex_workcell_storage_policy_contract()),
        "storage-policy-verifier-json": _write(tmp_path / "policy_verifier.json", {"verification_status": "storage_policy_verified"}),
        "memory-candidate-bundle-json": _write(tmp_path / "bundle.json", {"candidate_ledger_entries": [{"candidate_entry_id": "e1", "source_input_id": "matrix_json", "would_be_record_type": "matrix_receipt", "source_artifact_digest": "abc", "parent_entry_id": "p", "parent_entry_digest": "pd"}], "candidate_glow_items": [{"candidate_glow_item_id": "g1", "source_input_id": "matrix_json", "would_be_archive_item_type": "matrix_report_snapshot", "source_digest": "def", "related_candidate_ledger_entry_id": "e1"}]}),
        "memory-candidate-verifier-json": _write(tmp_path / "candidate_verifier.json", {"verification_status": "memory_candidate_bundle_verified"}),
        "vow-boundary-contract-json": _write(tmp_path / "vow.json", {"canonical_vow_digest": "vow"}),
        "vow-alignment-attestation-json": _write(tmp_path / "attest.json", {"failed_attestation_count": 0, "warning_attestation_count": 0}),
    }
    args = [sys.executable, str(SCRIPT), "--output", str(output), "--markdown-output", str(markdown), "--commit-sha", "abc123", "--pr-title", "title | newline\ncell", "--summary"]
    for flag, path in files.items():
        args += [f"--{flag}", str(path)]
    return args, output, markdown


def test_cli_writes_json_markdown_and_summary_deterministically(tmp_path: Path) -> None:
    args, output, markdown = _args(tmp_path)
    first = subprocess.run(args, check=True, text=True, capture_output=True)
    first_json = output.read_text(encoding="utf-8")
    first_md = markdown.read_text(encoding="utf-8")
    second = subprocess.run(args, check=True, text=True, capture_output=True)
    assert first.stdout == second.stdout
    assert first_json == output.read_text(encoding="utf-8")
    assert first_md == markdown.read_text(encoding="utf-8")
    summary = json.loads(first.stdout)
    assert summary["planned_ledger_transaction_count"] == 1
    data = json.loads(first_json)
    assert data["ledger_transaction_plan"][0]["planned_path"] == "/ledger/codex/workcell/abc123/matrix_receipt.json"
    assert "title \\| newline<br>cell" in first_md


@pytest.mark.parametrize(("filename", "contents"), [("bad.json", "{"), ("list.json", "[]")])
def test_invalid_or_non_object_required_json_exits_2(tmp_path: Path, filename: str, contents: str) -> None:
    args, _output, _markdown = _args(tmp_path)
    bad = tmp_path / filename
    bad.write_text(contents, encoding="utf-8")
    index = args.index("--storage-policy-verifier-json") + 1
    args[index] = str(bad)
    result = subprocess.run(args, text=True, capture_output=True)
    assert result.returncode == 2


def test_missing_required_json_path_exits_2(tmp_path: Path) -> None:
    args, _output, _markdown = _args(tmp_path)
    index = args.index("--storage-policy-verifier-json") + 1
    args[index] = str(tmp_path / "missing.json")
    result = subprocess.run(args, text=True, capture_output=True)
    assert result.returncode == 2
