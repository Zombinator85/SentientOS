from __future__ import annotations

import json
from pathlib import Path

from sentientos.kernel_admission_provenance import verify_kernel_admission_provenance


def _decision(*, correlation_id: str, action_kind: str, final_disposition: str = "allow") -> dict[str, object]:
    intent_by_action = {
        "lineage_integrate": {
            "domains": ["genesisforge_lineage_proposal_adoption"],
            "authority_classes": ["manifest_or_identity_mutation"],
        },
        "proposal_adopt": {
            "domains": ["genesisforge_lineage_proposal_adoption"],
            "authority_classes": ["proposal_adoption"],
        },
        "generate_immutable_manifest": {
            "domains": ["immutable_manifest_identity_writes"],
            "authority_classes": ["manifest_or_identity_mutation"],
        },
        "quarantine_clear": {
            "domains": ["quarantine_clear_privileged_operator_action"],
            "authority_classes": ["privileged_operator_control"],
        },
    }
    authority_by_action = {
        "lineage_integrate": "manifest_or_identity_mutation",
        "proposal_adopt": "proposal_adoption",
        "generate_immutable_manifest": "manifest_or_identity_mutation",
        "quarantine_clear": "privileged_operator_control",
    }
    payload: dict[str, object] = {
        "correlation_id": correlation_id,
        "admission_decision_ref": f"kernel_decision:{correlation_id}",
        "action_kind": action_kind,
        "authority_class": authority_by_action.get(action_kind, "test_authority"),
        "lifecycle_phase": "maintenance",
        "final_disposition": final_disposition,
    }
    intent = intent_by_action.get(action_kind)
    if intent is not None:
        payload["protected_mutation_intent"] = {
            "schema_version": 1,
            "declared": True,
            "domains": intent["domains"],
            "authority_classes": intent["authority_classes"],
            "expect_forward_enforcement": True,
            "invocation_path": "tests",
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
        {
            "correlation_id": "lineage-1",
            "admission_decision_ref": "kernel_decision:lineage-1",
            "action_kind": "lineage_integrate",
            "authority_class": "manifest_or_identity_mutation",
            "lifecycle_phase": "maintenance",
            "final_disposition": "allow",
            "execution_owner": "operator_cli",
        },
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
    status_counts = payload["protected_intent_status_counts"]  # type: ignore[index]
    assert status_counts["declared_and_consistent"] >= 3


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


def test_verify_kernel_admission_provenance_reports_undeclared_protected_action(tmp_path: Path) -> None:
    _append_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        {
            "correlation_id": "manifest-1",
            "admission_decision_ref": "kernel_decision:manifest-1",
            "action_kind": "generate_immutable_manifest",
            "authority_class": "manifest_or_identity_mutation",
            "lifecycle_phase": "maintenance",
            "final_disposition": "allow",
            "execution_owner": "operator_cli",
        },
    )
    payload = verify_kernel_admission_provenance(repo_root=tmp_path, mode="forward-enforcement")
    statuses = payload["protected_intent_status_counts"]  # type: ignore[index]
    assert statuses["undeclared_but_protected_action"] == 1
    issue_codes = {item["code"] for item in payload["issues"]}  # type: ignore[index]
    assert "protected_intent_undeclared_but_protected_action" in issue_codes


def test_verify_kernel_admission_provenance_reports_mismatched_declared_domain(tmp_path: Path) -> None:
    _append_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        {
            "correlation_id": "manifest-1",
            "admission_decision_ref": "kernel_decision:manifest-1",
            "action_kind": "generate_immutable_manifest",
            "authority_class": "manifest_or_identity_mutation",
            "lifecycle_phase": "maintenance",
            "final_disposition": "allow",
            "execution_owner": "operator_cli",
            "protected_mutation_intent": {
                "schema_version": 1,
                "declared": True,
                "domains": ["genesisforge_lineage_proposal_adoption"],
                "authority_classes": ["manifest_or_identity_mutation"],
                "expect_forward_enforcement": True,
                "invocation_path": "tests",
            },
        },
    )
    payload = verify_kernel_admission_provenance(repo_root=tmp_path, mode="forward-enforcement")
    statuses = payload["protected_intent_status_counts"]  # type: ignore[index]
    assert statuses["declared_but_mismatched"] == 1


def test_verify_kernel_admission_provenance_reports_declared_not_applicable(tmp_path: Path) -> None:
    _append_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        {
            "correlation_id": "obs-1",
            "admission_decision_ref": "kernel_decision:obs-1",
            "action_kind": "view_status",
            "authority_class": "observation",
            "lifecycle_phase": "runtime",
            "final_disposition": "allow",
            "execution_owner": "operator_cli",
            "protected_mutation_intent": {
                "schema_version": 1,
                "declared": True,
                "domains": ["immutable_manifest_identity_writes"],
                "authority_classes": ["observation"],
                "expect_forward_enforcement": True,
                "invocation_path": "tests",
            },
        },
    )
    payload = verify_kernel_admission_provenance(repo_root=tmp_path)
    statuses = payload["protected_intent_status_counts"]  # type: ignore[index]
    assert statuses["declared_but_not_applicable"] == 1


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


def test_verify_kernel_admission_provenance_summary_legacy_only_in_baseline_aware_mode(tmp_path: Path) -> None:
    _append_jsonl(
        tmp_path / "lineage/lineage.jsonl",
        {"proposal_id": "legacy-lineage-entry-without-admission"},
    )
    payload = verify_kernel_admission_provenance(repo_root=tmp_path, strict=False)
    summary = payload["summary"]  # type: ignore[index]
    assert summary["mode"] == "baseline-aware"
    assert summary["overall_status"] == "legacy_only"
    assert summary["has_only_legacy_issues"] is True
    assert summary["has_current_contract_violations"] is False
    assert summary["ok"] is True
    assert summary["counts"]["classification"]["legacy_missing_admission_link"] == 1


def test_verify_kernel_admission_provenance_summary_legacy_only_in_forward_enforcement_mode(tmp_path: Path) -> None:
    _append_jsonl(
        tmp_path / "lineage/lineage.jsonl",
        {"proposal_id": "legacy-lineage-entry-without-admission"},
    )
    payload = verify_kernel_admission_provenance(repo_root=tmp_path, mode="forward-enforcement")
    summary = payload["summary"]  # type: ignore[index]
    assert summary["mode"] == "forward-enforcement"
    assert summary["overall_status"] == "legacy_only"
    assert summary["has_only_legacy_issues"] is True
    assert summary["ok"] is True
    assert summary["legacy_debt_count"] == 1
    assert summary["fresh_regression_count"] == 0


def test_verify_kernel_admission_provenance_summary_legacy_only_is_blocking_in_strict_mode(tmp_path: Path) -> None:
    _append_jsonl(
        tmp_path / "lineage/lineage.jsonl",
        {"proposal_id": "legacy-lineage-entry-without-admission"},
    )
    payload = verify_kernel_admission_provenance(repo_root=tmp_path, strict=True)
    summary = payload["summary"]  # type: ignore[index]
    assert summary["mode"] == "strict"
    assert summary["overall_status"] == "legacy_only"
    assert summary["has_only_legacy_issues"] is True
    assert summary["ok"] is False
    assert summary["counts"]["blocking_issue_count"] == 1


def test_verify_kernel_admission_provenance_forward_enforcement_blocks_current_malformed(tmp_path: Path) -> None:
    _append_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        {
            "correlation_id": "manifest-1",
            "admission_decision_ref": "kernel_decision:manifest-1",
            "action_kind": "generate_immutable_manifest",
            "authority_class": "manifest_or_identity_mutation",
            "lifecycle_phase": "maintenance",
            "final_disposition": "allow",
        },
    )
    payload = verify_kernel_admission_provenance(repo_root=tmp_path, mode="forward-enforcement")
    summary = payload["summary"]  # type: ignore[index]
    assert summary["mode"] == "forward-enforcement"
    assert summary["ok"] is False
    assert summary["malformed_current_contract_count"] >= 1
    assert summary["active_contradiction_count"] == 0


def test_verify_kernel_admission_provenance_forward_enforcement_blocks_active_contradictions(tmp_path: Path) -> None:
    decisions = tmp_path / "glow/control_plane/kernel_decisions.jsonl"
    _append_jsonl(decisions, _decision(correlation_id="dup", action_kind="lineage_integrate"))
    _append_jsonl(decisions, _decision(correlation_id="dup", action_kind="proposal_adopt"))
    payload = verify_kernel_admission_provenance(repo_root=tmp_path, mode="forward-enforcement")
    summary = payload["summary"]  # type: ignore[index]
    assert summary["ok"] is False
    assert summary["active_contradiction_count"] == 1


def test_verify_kernel_admission_provenance_summary_current_violation_present(tmp_path: Path) -> None:
    _append_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        {
            "correlation_id": "manifest-1",
            "admission_decision_ref": "kernel_decision:manifest-1",
            "action_kind": "generate_immutable_manifest",
            "authority_class": "manifest_or_identity_mutation",
            "lifecycle_phase": "maintenance",
            "final_disposition": "allow",
        },
    )
    payload = verify_kernel_admission_provenance(repo_root=tmp_path, strict=False)
    summary = payload["summary"]  # type: ignore[index]
    assert summary["overall_status"] == "current_violation_present"
    assert summary["has_current_contract_violations"] is True
    assert summary["has_only_legacy_issues"] is False
    assert summary["ok"] is False
    assert summary["counts"]["classification"]["malformed_current_contract"] == 1


def test_verify_kernel_admission_provenance_strict_remains_stricter_than_forward(tmp_path: Path) -> None:
    _append_jsonl(
        tmp_path / "lineage/lineage.jsonl",
        {"proposal_id": "legacy-lineage-entry-without-admission"},
    )
    forward_payload = verify_kernel_admission_provenance(repo_root=tmp_path, mode="forward-enforcement")
    strict_payload = verify_kernel_admission_provenance(repo_root=tmp_path, strict=True)
    assert forward_payload["ok"] is True
    assert strict_payload["ok"] is False
    issue = forward_payload["issues"][0]  # type: ignore[index]
    assert issue["enforcement_class"] == "legacy_debt"
