from __future__ import annotations

import json
from pathlib import Path

from sentientos.kernel_admission_provenance import verify_kernel_admission_provenance


def _decision(*, correlation_id: str, action_kind: str, final_disposition: str = "allow") -> dict[str, object]:
    payload: dict[str, object] = {
        "correlation_id": correlation_id,
        "admission_decision_ref": f"kernel_decision:{correlation_id}",
        "action_kind": action_kind,
        "authority_class": "test_authority",
        "lifecycle_phase": "maintenance",
        "final_disposition": final_disposition,
    }
    if final_disposition == "allow":
        payload["execution_owner"] = "tester"
    return payload


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
        _decision(correlation_id="corr-1", action_kind="lineage_integrate"),
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
        _decision(correlation_id="lineage-1", action_kind="lineage_integrate"),
    )
    _append_jsonl(
        decisions,
        _decision(correlation_id="manifest-1", action_kind="generate_immutable_manifest"),
    )
    _append_jsonl(
        decisions,
        _decision(correlation_id="qc-1", action_kind="quarantine_clear"),
    )
    _append_jsonl(
        decisions,
        _decision(correlation_id="repair-1", action_kind="restart_daemon"),
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
                "action_kind": "generate_immutable_manifest",
                "authority_class": "manifest_or_identity_mutation",
                "lifecycle_phase": "maintenance",
                "final_disposition": "allow",
                "execution_owner": "operator_cli",
            }
        },
    )
    _append_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        {
            "event": "integrity_recovered",
            "correlation_id": "qc-1",
            "admission_decision_ref": "kernel_decision:qc-1",
            "action_kind": "quarantine_clear",
            "authority_class": "privileged_operator_control",
            "lifecycle_phase": "maintenance",
            "final_disposition": "allow",
            "execution_owner": "operator_cli",
        },
    )
    _append_jsonl(
        tmp_path / "glow/forge/recovery_ledger.jsonl",
        {
            "status": "auto-repair verified",
            "details": {
                "kernel_admission": {
                    "correlation_id": "repair-1",
                    "admission_decision_ref": "kernel_decision:repair-1",
                    "action_kind": "restart_daemon",
                    "authority_class": "repair",
                    "lifecycle_phase": "runtime",
                    "final_disposition": "allow",
                    "execution_owner": "codex_healer",
                }
            },
        },
    )

    payload = verify_kernel_admission_provenance(repo_root=tmp_path)
    assert payload["ok"] is True


def test_verify_kernel_admission_provenance_detects_correlation_collision(tmp_path: Path) -> None:
    decisions = tmp_path / "glow/control_plane/kernel_decisions.jsonl"
    _append_jsonl(decisions, _decision(correlation_id="dup", action_kind="lineage_integrate"))
    _append_jsonl(decisions, _decision(correlation_id="dup", action_kind="proposal_adopt"))

    payload = verify_kernel_admission_provenance(repo_root=tmp_path)
    assert payload["ok"] is False
    issue_codes = {item["code"] for item in payload["issues"]}  # type: ignore[index]
    assert "correlation_action_kind_collision" in issue_codes


def test_verify_kernel_admission_provenance_detects_missing_required_allow_fields(tmp_path: Path) -> None:
    decisions = tmp_path / "glow/control_plane/kernel_decisions.jsonl"
    _append_jsonl(
        decisions,
        {
            "correlation_id": "manifest-1",
            "admission_decision_ref": "kernel_decision:manifest-1",
            "action_kind": "generate_immutable_manifest",
            "authority_class": "manifest_or_identity_mutation",
            "lifecycle_phase": "maintenance",
            "final_disposition": "allow",
        },
    )
    payload = verify_kernel_admission_provenance(repo_root=tmp_path)
    issue_codes = {item["code"] for item in payload["issues"]}  # type: ignore[index]
    assert "decision_missing_required_allow_fields" in issue_codes


def test_verify_kernel_admission_provenance_detects_malformed_linkage(tmp_path: Path) -> None:
    decisions = tmp_path / "glow/control_plane/kernel_decisions.jsonl"
    _append_jsonl(decisions, _decision(correlation_id="qc-1", action_kind="quarantine_clear"))
    _append_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        {
            "event": "integrity_recovered",
            "correlation_id": "qc-1",
            "admission_decision_ref": "kernel_decision:not-qc-1",
            "action_kind": "quarantine_clear",
            "authority_class": "privileged_operator_control",
            "lifecycle_phase": "maintenance",
            "final_disposition": "allow",
            "execution_owner": "operator_cli",
        },
    )
    payload = verify_kernel_admission_provenance(repo_root=tmp_path)
    issue_codes = {item["code"] for item in payload["issues"]}  # type: ignore[index]
    assert "invalid_quarantine_admission_ref" in issue_codes
