from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import build_local_effect_transaction_ledger as script
from sentientos.local_diagnostic_effect import run_local_diagnostic_effect_wing, run_local_diagnostic_exact_rollback_wing

pytestmark = pytest.mark.no_legacy_skip


def _write(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _record_files(tmp_path: Path) -> dict[str, Path]:
    effect_dir = tmp_path / "effect"
    records = run_local_diagnostic_effect_wing(output_dir=effect_dir)
    return {
        "effect": _write(tmp_path / "effect_receipt.json", records.receipt.to_dict()),
        "post": _write(tmp_path / "postcondition_check.json", records.postcondition_check.to_dict()),
        "audit": _write(tmp_path / "production_audit.json", records.production_audit_receipt.to_dict()),
        "plan": _write(tmp_path / "rollback_plan.json", records.rollback_plan.to_dict()),
    }


def test_cli_requires_required_record_paths() -> None:
    assert script.main([]) == 2


def test_cli_builds_summary_from_record_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    files = _record_files(tmp_path)
    assert script.main(["--effect-receipt", str(files["effect"]), "--postcondition-check", str(files["post"]), "--production-audit", str(files["audit"]), "--rollback-plan", str(files["plan"]), "--summary"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ledger"]["ledger_status"] == "local_effect_transaction_ledger_incomplete"
    assert payload["lifecycle_report"]["lifecycle_status"] == "local_effect_lifecycle_rollback_pending"
    assert payload["host_mutation_performed"] is False
    assert payload["subprocess_performed"] is False
    assert payload["shell_performed"] is False


def test_cli_writes_explicit_output_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    files = _record_files(tmp_path)
    output = tmp_path / "ledger.json"
    before = set(tmp_path.rglob("*"))
    assert script.main(["--effect-receipt", str(files["effect"]), "--postcondition-check", str(files["post"]), "--production-audit", str(files["audit"]), "--rollback-plan", str(files["plan"]), "--output", str(output), "--summary"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert output.exists()
    assert set(tmp_path.rglob("*")) - before == {output}
    assert payload["artifact_receipt"]["output_path"] == str(output)


def test_cli_refuses_unsafe_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    files = _record_files(tmp_path)
    assert script.main(["--effect-receipt", str(files["effect"]), "--postcondition-check", str(files["post"]), "--production-audit", str(files["audit"]), "--rollback-plan", str(files["plan"]), "--output", str(tmp_path)]) == 2
    assert "directory" in capsys.readouterr().err


def test_cli_full_rollback_records_close_transaction(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    effect_dir = tmp_path / "effect"
    records = run_local_diagnostic_effect_wing(output_dir=effect_dir)
    rollback = run_local_diagnostic_exact_rollback_wing(records.receipt, records.rollback_plan, output_dir_scope=effect_dir)
    paths = {
        "effect": _write(tmp_path / "effect_receipt.json", records.receipt.to_dict()),
        "post": _write(tmp_path / "postcondition_check.json", records.postcondition_check.to_dict()),
        "audit": _write(tmp_path / "production_audit.json", records.production_audit_receipt.to_dict()),
        "plan": _write(tmp_path / "rollback_plan.json", records.rollback_plan.to_dict()),
        "rollback": _write(tmp_path / "rollback_receipt.json", rollback.receipt.to_dict()),
        "rollback_post": _write(tmp_path / "rollback_postcondition_check.json", rollback.postcondition_check.to_dict()),
        "rollback_audit": _write(tmp_path / "rollback_audit.json", rollback.audit_receipt.to_dict()),
    }
    assert script.main(["--effect-receipt", str(paths["effect"]), "--postcondition-check", str(paths["post"]), "--production-audit", str(paths["audit"]), "--rollback-plan", str(paths["plan"]), "--rollback-receipt", str(paths["rollback"]), "--rollback-postcondition-check", str(paths["rollback_post"]), "--rollback-audit", str(paths["rollback_audit"]), "--summary"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ledger"]["current_transaction_status"] == "local_effect_transaction_closed"
