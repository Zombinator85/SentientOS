from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_workspace_file_transaction_ledger import main
from sentientos.workspace_file_effect import run_workspace_file_effect_wing

pytestmark = pytest.mark.no_legacy_skip


def _write_records(tmp_path: Path) -> None:
    records = run_workspace_file_effect_wing(workspace_root=tmp_path, relative_target_path="demo.txt", payload_text="hello")
    mapping = {
        "preimage.json": records.preimage,
        "effect_receipt.json": records.receipt,
        "postcondition.json": records.postcondition,
        "audit.json": records.production_audit,
        "rollback_plan.json": records.rollback_plan,
    }
    for name, record in mapping.items():
        (tmp_path / name).write_text(json.dumps(record.to_dict()), encoding="utf-8")


def test_workspace_transaction_ledger_cli_summary_and_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_records(tmp_path)
    out = tmp_path / "ledger.json"
    code = main([
        "--effect-receipt", str(tmp_path / "effect_receipt.json"),
        "--preimage", str(tmp_path / "preimage.json"),
        "--postcondition-check", str(tmp_path / "postcondition.json"),
        "--production-audit", str(tmp_path / "audit.json"),
        "--rollback-plan", str(tmp_path / "rollback_plan.json"),
        "--output", str(out),
        "--summary",
    ])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["metadata_only"] is True
    assert payload["lifecycle_report"]["lifecycle_status"] == "workspace_file_lifecycle_rollback_pending"
    assert payload["artifact_receipt"]["host_mutation_performed"] is True
    assert out.exists()
