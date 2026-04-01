from __future__ import annotations

import json
from pathlib import Path

from sentientos.kernel_admission_provenance import verify_kernel_admission_provenance


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def test_verify_kernel_admission_provenance_detects_missing_links(tmp_path: Path) -> None:
    decisions = tmp_path / "glow/control_plane/kernel_decisions.jsonl"
    _append_jsonl(
        decisions,
        {"correlation_id": "corr-1", "action_kind": "lineage_integrate", "final_disposition": "allow"},
    )
    _append_jsonl(tmp_path / "lineage/lineage.jsonl", {"proposal_id": "p-1"})

    payload = verify_kernel_admission_provenance(repo_root=tmp_path)
    assert payload["ok"] is False
    issue_codes = {item["code"] for item in payload["issues"]}  # type: ignore[index]
    assert "missing_lineage_admission_link" in issue_codes


def test_verify_kernel_admission_provenance_happy_path(tmp_path: Path) -> None:
    decisions = tmp_path / "glow/control_plane/kernel_decisions.jsonl"
    _append_jsonl(
        decisions,
        {"correlation_id": "lineage-1", "action_kind": "lineage_integrate", "final_disposition": "allow"},
    )
    _append_jsonl(
        decisions,
        {"correlation_id": "manifest-1", "action_kind": "generate_immutable_manifest", "final_disposition": "allow"},
    )
    _append_jsonl(
        decisions,
        {"correlation_id": "qc-1", "action_kind": "quarantine_clear", "final_disposition": "allow"},
    )
    _append_jsonl(
        decisions,
        {"correlation_id": "repair-1", "action_kind": "restart_daemon", "final_disposition": "allow"},
    )

    _append_jsonl(
        tmp_path / "lineage/lineage.jsonl",
        {"correlation_id": "lineage-1", "admission_decision_ref": "kernel_decision:lineage-1"},
    )
    _write_json(
        tmp_path / "vow/immutable_manifest.json",
        {
            "admission": {
                "correlation_id": "manifest-1",
                "admission_decision_ref": "kernel_decision:manifest-1",
            }
        },
    )
    _append_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        {"event": "integrity_recovered", "correlation_id": "qc-1"},
    )
    _append_jsonl(
        tmp_path / "glow/forge/recovery_ledger.jsonl",
        {
            "status": "auto-repair verified",
            "details": {"kernel_admission": {"correlation_id": "repair-1", "final_disposition": "allow"}},
        },
    )

    payload = verify_kernel_admission_provenance(repo_root=tmp_path)
    assert payload["ok"] is True


def test_verify_kernel_admission_provenance_detects_correlation_collision(tmp_path: Path) -> None:
    decisions = tmp_path / "glow/control_plane/kernel_decisions.jsonl"
    _append_jsonl(decisions, {"correlation_id": "dup", "action_kind": "lineage_integrate", "final_disposition": "allow"})
    _append_jsonl(decisions, {"correlation_id": "dup", "action_kind": "proposal_adopt", "final_disposition": "allow"})

    payload = verify_kernel_admission_provenance(repo_root=tmp_path)
    assert payload["ok"] is False
    issue_codes = {item["code"] for item in payload["issues"]}  # type: ignore[index]
    assert "correlation_action_kind_collision" in issue_codes
