from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_storage_policy_contract import build_codex_workcell_storage_policy_contract
from sentientos.codex_workcell_storage_transaction_plan import build_codex_workcell_storage_transaction_plan

SCRIPT = Path("scripts/verify_codex_workcell_storage_transaction_plan.py")


def _write(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    return path


def _plan() -> dict:
    return build_codex_workcell_storage_transaction_plan(storage_policy_contract=build_codex_workcell_storage_policy_contract(), storage_policy_verifier={"verification_status": "storage_policy_verified"}, memory_candidate_bundle={"candidate_ledger_entries": [{"candidate_entry_id": "e1", "source_input_id": "matrix_json", "would_be_record_type": "matrix_receipt", "source_artifact_digest": "abc", "parent_entry_id": "p", "parent_entry_digest": "pd"}], "candidate_glow_items": [{"candidate_glow_item_id": "g1", "source_input_id": "matrix_json", "would_be_archive_item_type": "matrix_report_snapshot", "source_digest": "def", "related_candidate_ledger_entry_id": "e1"}]}, memory_candidate_verifier={"verification_status": "memory_candidate_bundle_verified"}, vow_boundary_contract={"canonical_vow_digest": "vow"}, vow_alignment_attestation={"failed_attestation_count": 0}, commit_sha="abc123")


def test_cli_writes_json_markdown_and_summary(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    markdown = tmp_path / "report.md"
    plan = _write(tmp_path / "plan.json", _plan())
    contract = _write(tmp_path / "contract.json", {"storage_policy_contract_id": "contract.v1"})
    verifier = _write(tmp_path / "verifier.json", {"storage_policy_verifier_id": "verifier.v1", "verification_status": "storage_policy_verified"})
    args = [sys.executable, str(SCRIPT), "--storage-transaction-plan-json", str(plan), "--storage-policy-contract-json", str(contract), "--storage-policy-verifier-json", str(verifier), "--output", str(output), "--markdown-output", str(markdown), "--summary"]
    first = subprocess.run(args, check=True, text=True, capture_output=True)
    first_json = output.read_text(encoding="utf-8")
    first_md = markdown.read_text(encoding="utf-8")
    second = subprocess.run(args, check=True, text=True, capture_output=True)
    assert first.stdout == second.stdout
    assert first_json == output.read_text(encoding="utf-8")
    assert first_md == markdown.read_text(encoding="utf-8")
    summary = json.loads(first.stdout)
    assert summary["verification_status"] == "storage_transaction_plan_verified"
    assert json.loads(first_json)["optional_context_summary"][0]["provided"] is True
    assert "Codex Workcell Storage Transaction Plan Verifier" in first_md


@pytest.mark.parametrize("contents", ["{", "[]"])
def test_invalid_or_non_object_transaction_plan_json_exits_2(tmp_path: Path, contents: str) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(contents, encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), "--storage-transaction-plan-json", str(bad), "--output", str(tmp_path / "out.json")], text=True, capture_output=True)
    assert result.returncode == 2


def test_missing_transaction_plan_path_exits_2(tmp_path: Path) -> None:
    result = subprocess.run([sys.executable, str(SCRIPT), "--storage-transaction-plan-json", str(tmp_path / "missing.json"), "--output", str(tmp_path / "out.json")], text=True, capture_output=True)
    assert result.returncode == 2


def test_invalid_optional_context_json_exits_2(tmp_path: Path) -> None:
    plan = _write(tmp_path / "plan.json", _plan())
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), "--storage-transaction-plan-json", str(plan), "--storage-policy-contract-json", str(bad), "--output", str(tmp_path / "out.json")], text=True, capture_output=True)
    assert result.returncode == 2
