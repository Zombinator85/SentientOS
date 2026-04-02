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
    assert summary["counts"]["classification"]["malformed_current_contract"] >= 1


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


def test_execution_consistency_declared_admitted_side_effect_match_is_consistent(tmp_path: Path) -> None:
    _append_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        _decision(correlation_id="manifest-1", action_kind="generate_immutable_manifest"),
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
    payload = verify_kernel_admission_provenance(repo_root=tmp_path)
    checks = payload["execution_consistency_checks"]  # type: ignore[index]
    assert checks[0]["status"] == "consistent"


def test_execution_consistency_reports_declared_domain_mismatch(tmp_path: Path) -> None:
    _append_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        {
            **_decision(correlation_id="manifest-1", action_kind="generate_immutable_manifest"),
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
    _write_json(
        tmp_path / "vow/immutable_manifest.json",
        {"admission": _decision(correlation_id="manifest-1", action_kind="generate_immutable_manifest")},
    )
    payload = verify_kernel_admission_provenance(repo_root=tmp_path, mode="forward-enforcement")
    status_counts = payload["execution_consistency_status_counts"]  # type: ignore[index]
    assert status_counts["declared_domain_mismatch"] == 1


def test_execution_consistency_reports_declared_authority_mismatch(tmp_path: Path) -> None:
    manifest_decision = _decision(correlation_id="manifest-1", action_kind="generate_immutable_manifest")
    manifest_decision["protected_mutation_intent"] = {
        "schema_version": 1,
        "declared": True,
        "domains": ["immutable_manifest_identity_writes"],
        "authority_classes": ["proposal_adoption"],
        "expect_forward_enforcement": True,
        "invocation_path": "tests",
    }
    _append_jsonl(tmp_path / "glow/control_plane/kernel_decisions.jsonl", manifest_decision)
    _write_json(tmp_path / "vow/immutable_manifest.json", {"admission": manifest_decision})
    payload = verify_kernel_admission_provenance(repo_root=tmp_path, mode="forward-enforcement")
    status_counts = payload["execution_consistency_status_counts"]  # type: ignore[index]
    assert status_counts["declared_authority_mismatch"] == 1


def test_execution_consistency_reports_missing_expected_side_effect(tmp_path: Path) -> None:
    _append_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        _decision(correlation_id="manifest-1", action_kind="generate_immutable_manifest"),
    )
    payload = verify_kernel_admission_provenance(repo_root=tmp_path, mode="forward-enforcement")
    status_counts = payload["execution_consistency_status_counts"]  # type: ignore[index]
    assert status_counts["admitted_but_missing_expected_side_effect"] == 1
    assert payload["ok"] is False


def test_execution_consistency_reports_undeclared_side_effect_drift(tmp_path: Path) -> None:
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
    payload = verify_kernel_admission_provenance(repo_root=tmp_path, mode="forward-enforcement")
    outcome_counts = payload["execution_consistency_outcome_counts"]  # type: ignore[index]
    assert outcome_counts["execution_drift_detected"] == 1


def test_execution_consistency_summary_vocabulary_is_stable(tmp_path: Path) -> None:
    _append_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        _decision(correlation_id="manifest-1", action_kind="generate_immutable_manifest"),
    )
    _write_json(
        tmp_path / "vow/immutable_manifest.json",
        {"admission": _decision(correlation_id="manifest-1", action_kind="generate_immutable_manifest")},
    )
    payload = verify_kernel_admission_provenance(repo_root=tmp_path)
    consistency = payload["summary"]["execution_consistency"]  # type: ignore[index]
    assert consistency["status_vocabulary"] == [  # type: ignore[index]
        "consistent",
        "declared_domain_mismatch",
        "declared_authority_mismatch",
        "side_effect_domain_mismatch",
        "admitted_but_missing_expected_side_effect",
        "undeclared_side_effect",
        "not_applicable",
    ]
    assert consistency["outcome_vocabulary"] == [  # type: ignore[index]
        "not_applicable",
        "declared_and_consistent",
        "declared_but_mismatched",
        "undeclared_but_protected_action",
        "execution_drift_detected",
        "admitted_but_missing_expected_side_effect",
    ]


def test_execution_consistency_covers_proposal_adopt_side_effects(tmp_path: Path) -> None:
    _append_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        _decision(correlation_id="adopt-1", action_kind="proposal_adopt"),
    )
    _write_json(
        tmp_path / "live/daemon-a.json",
        {"admission": _decision(correlation_id="adopt-1", action_kind="proposal_adopt")},
    )
    codex_index = tmp_path / "codex_index.json"
    codex_index.parent.mkdir(parents=True, exist_ok=True)
    codex_index.write_text(
        json.dumps(
            [
                {
                    "spec_id": "spec-a",
                    "admission": _decision(correlation_id="adopt-1", action_kind="proposal_adopt"),
                }
            ],
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    payload = verify_kernel_admission_provenance(
        repo_root=tmp_path,
        adoption_live_mount_path=tmp_path / "live",
        adoption_codex_index_path=tmp_path / "codex_index.json",
    )
    checks = payload["execution_consistency_checks"]  # type: ignore[index]
    assert checks[0]["status"] == "consistent"


def _non_bypass_model(*, canonical_boundary: str = "scripts/generate_immutable_manifest.py") -> dict[str, object]:
    return {
        "scope_id": "protected_mutation_proof:v1:covered_corridor",
        "model_version": "test",
        "status_vocabulary": [
            "no_obvious_bypass_detected",
            "alternate_writer_detected",
            "unadmitted_operator_path_detected",
            "uncovered_mutation_entrypoint_detected",
            "canonical_boundary_missing",
        ],
        "domains": [
            {
                "name": "immutable_manifest_identity_writes",
                "canonical_boundary": canonical_boundary,
                "expected_kernel_action_kinds": ["generate_immutable_manifest"],
                "expected_authority_classes": ["manifest_or_identity_mutation"],
                "protected_artifact_domains": ["vow/immutable_manifest.json"],
                "allowed_writer_surfaces": [canonical_boundary],
            }
        ],
    }


def test_non_bypass_no_alternate_writer_detected_for_canonical_path(tmp_path: Path) -> None:
    _append_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        _decision(correlation_id="manifest-1", action_kind="generate_immutable_manifest"),
    )
    _write_json(tmp_path / "vow/immutable_manifest.json", {"admission": _decision(correlation_id="manifest-1", action_kind="generate_immutable_manifest")})
    _write_json(tmp_path / "scripts/generate_immutable_manifest.py", {"placeholder": "admit_action('generate_immutable_manifest')"})
    payload = verify_kernel_admission_provenance(repo_root=tmp_path, non_bypass_model=_non_bypass_model())
    checks = payload["non_bypass_checks"]  # type: ignore[index]
    assert checks[0]["status"] == "no_obvious_bypass_detected"


def test_non_bypass_detects_alternate_writer(tmp_path: Path) -> None:
    _append_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        _decision(correlation_id="manifest-1", action_kind="generate_immutable_manifest"),
    )
    _write_json(tmp_path / "vow/immutable_manifest.json", {"admission": _decision(correlation_id="manifest-1", action_kind="generate_immutable_manifest")})
    canonical = tmp_path / "scripts/generate_immutable_manifest.py"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text("def run():\n    pass\n", encoding="utf-8")
    bypass = tmp_path / "sentientos/manifest_writer.py"
    bypass.parent.mkdir(parents=True, exist_ok=True)
    bypass.write_text("from pathlib import Path\nPath('vow/immutable_manifest.json').write_text('{}')\n", encoding="utf-8")
    payload = verify_kernel_admission_provenance(repo_root=tmp_path, mode="forward-enforcement", non_bypass_model=_non_bypass_model())
    checks = payload["non_bypass_checks"]  # type: ignore[index]
    assert checks[0]["status"] == "alternate_writer_detected"
    assert payload["ok"] is False


def test_non_bypass_detects_unadmitted_operator_path(tmp_path: Path) -> None:
    _append_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        _decision(correlation_id="manifest-1", action_kind="generate_immutable_manifest"),
    )
    _write_json(tmp_path / "vow/immutable_manifest.json", {"admission": _decision(correlation_id="manifest-1", action_kind="generate_immutable_manifest")})
    canonical = tmp_path / "scripts/generate_immutable_manifest.py"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text("def run():\n    pass\n", encoding="utf-8")
    bypass = tmp_path / "scripts/manual_manifest_override.py"
    bypass.parent.mkdir(parents=True, exist_ok=True)
    bypass.write_text("from pathlib import Path\nPath('vow/immutable_manifest.json').write_text('{}')\n", encoding="utf-8")
    payload = verify_kernel_admission_provenance(repo_root=tmp_path, mode="forward-enforcement", non_bypass_model=_non_bypass_model())
    checks = payload["non_bypass_checks"]  # type: ignore[index]
    assert checks[0]["status"] == "unadmitted_operator_path_detected"


def test_non_bypass_detects_missing_canonical_boundary_mapping(tmp_path: Path) -> None:
    _append_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        _decision(correlation_id="manifest-1", action_kind="generate_immutable_manifest"),
    )
    _write_json(tmp_path / "vow/immutable_manifest.json", {"admission": _decision(correlation_id="manifest-1", action_kind="generate_immutable_manifest")})
    payload = verify_kernel_admission_provenance(
        repo_root=tmp_path,
        non_bypass_model=_non_bypass_model(canonical_boundary=""),
    )
    checks = payload["non_bypass_checks"]  # type: ignore[index]
    assert checks[0]["status"] == "canonical_boundary_missing"


def test_non_bypass_forward_blocks_fresh_and_strict_at_least_as_strict(tmp_path: Path) -> None:
    _append_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        _decision(correlation_id="manifest-1", action_kind="generate_immutable_manifest"),
    )
    _write_json(tmp_path / "vow/immutable_manifest.json", {"admission": _decision(correlation_id="manifest-1", action_kind="generate_immutable_manifest")})
    canonical = tmp_path / "scripts/generate_immutable_manifest.py"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text("def run():\n    pass\n", encoding="utf-8")
    bypass = tmp_path / "scripts/manual_manifest_override.py"
    bypass.parent.mkdir(parents=True, exist_ok=True)
    bypass.write_text("from pathlib import Path\nPath('vow/immutable_manifest.json').write_text('{}')\n", encoding="utf-8")
    forward = verify_kernel_admission_provenance(repo_root=tmp_path, mode="forward-enforcement", non_bypass_model=_non_bypass_model())
    strict = verify_kernel_admission_provenance(repo_root=tmp_path, strict=True, non_bypass_model=_non_bypass_model())
    assert forward["ok"] is False
    assert strict["ok"] is False
    forward_summary = forward["summary"]["non_bypass"]  # type: ignore[index]
    strict_summary = strict["summary"]["non_bypass"]  # type: ignore[index]
    assert forward_summary["fresh_violation_blocking_in_mode"] is True
    assert strict_summary["fresh_violation_blocking_in_mode"] is True


def test_non_bypass_status_vocabulary_is_stable(tmp_path: Path) -> None:
    _append_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        _decision(correlation_id="manifest-1", action_kind="generate_immutable_manifest"),
    )
    _write_json(tmp_path / "vow/immutable_manifest.json", {"admission": _decision(correlation_id="manifest-1", action_kind="generate_immutable_manifest")})
    canonical = tmp_path / "scripts/generate_immutable_manifest.py"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text("def run():\n    pass\n", encoding="utf-8")
    payload = verify_kernel_admission_provenance(repo_root=tmp_path, non_bypass_model=_non_bypass_model())
    non_bypass = payload["summary"]["non_bypass"]  # type: ignore[index]
    assert non_bypass["status_vocabulary"] == [  # type: ignore[index]
        "no_obvious_bypass_detected",
        "alternate_writer_detected",
        "unadmitted_operator_path_detected",
        "uncovered_mutation_entrypoint_detected",
        "canonical_boundary_missing",
    ]
