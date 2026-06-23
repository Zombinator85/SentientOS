from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_architecture import build_codex_workcell_architecture, render_codex_workcell_architecture_markdown

REQUIRED_COMPONENTS = {
    "user_intent_ingress", "codex_task_workspace", "bootstrap_scaffold", "focused_tests", "targeted_mypy",
    "review_packet_matrix", "codex_task_lifecycle_summary", "codex_lifecycle_doctor", "codex_landing_evidence_index",
    "codex_landing_evidence_appendix", "codex_beneficial_trait_doctrine", "appendix_provenance_sidecar",
    "codex_finalize_landing", "codex_pr_metadata_guard", "git_commit_boundary", "pr_metadata_boundary",
    "sentientos_ledger", "glow_archive", "pulse_monitor", "daemon_repair_substrate", "vow_digest",
    "federation_consensus_boundary",
}

REQUIRED_FLOWS = {
    "intent_to_bootstrap", "bootstrap_to_task_workspace", "task_workspace_to_focused_proof", "focused_proof_to_matrix",
    "matrix_to_finalizer", "matrix_to_lifecycle_summary", "lifecycle_summary_to_doctor", "artifacts_to_evidence_index",
    "index_doctor_doctrine_to_appendix", "appendix_to_reviewer_surface", "finalizer_to_commit_boundary",
    "pr_metadata_finalizer_to_guard", "guard_to_pr_metadata_boundary", "landed_receipts_to_ledger",
    "evidence_to_glow_archive", "stale_or_pressure_signal_to_pulse", "pulse_to_daemon_repair_recommendation",
    "daemon_to_future_codex_task", "federation_consensus_to_drift_control",
}

REQUIRED_NON_AUTHORITY = {
    "architecture_map_is_metadata_only", "architecture_map_is_descriptive_only", "architecture_map_does_not_decide_readiness",
    "architecture_map_does_not_authorize_commit", "architecture_map_does_not_authorize_pr_metadata",
    "architecture_map_does_not_run_commands", "architecture_map_does_not_schedule_work",
    "architecture_map_does_not_execute_runtime_actions", "architecture_map_does_not_train_or_modify_models",
    "architecture_map_does_not_create_new_gates",
}


def _components_by_id() -> dict[str, dict[str, object]]:
    return {component["component_id"]: component for component in build_codex_workcell_architecture()["components"]}


def test_all_required_component_ids_are_present() -> None:
    assert REQUIRED_COMPONENTS <= set(_components_by_id())


def test_all_required_flow_ids_are_present() -> None:
    architecture = build_codex_workcell_architecture()
    assert REQUIRED_FLOWS <= {flow["flow_id"] for flow in architecture["flows"]}


def test_every_flow_references_known_components() -> None:
    architecture = build_codex_workcell_architecture()
    known = {component["component_id"] for component in architecture["components"]}
    for flow in architecture["flows"]:
        assert flow["source_component"] in known
        assert flow["target_component"] in known


def test_finalizer_and_guard_are_only_transition_authority_components() -> None:
    transition_components = {component["component_id"] for component in build_codex_workcell_architecture()["components"] if component["authority_level"] == "transition_authority"}
    assert transition_components == {"codex_finalize_landing", "codex_pr_metadata_guard"}


def test_review_surfaces_do_not_have_state_transition_power() -> None:
    for component in build_codex_workcell_architecture()["components"]:
        if component["authority_level"] in {"review_only", "archival_surface", "proof_signal", "future_integration"}:
            assert component["state_transition_power"] is False


def test_interpretive_and_catalog_surfaces_are_non_authoritative() -> None:
    components = _components_by_id()
    for component_id in {"codex_beneficial_trait_doctrine", "codex_landing_evidence_appendix", "appendix_provenance_sidecar", "codex_lifecycle_doctor", "codex_landing_evidence_index"}:
        assert components[component_id]["state_transition_power"] is False
        assert components[component_id]["authority_level"] == "review_only"


def test_sentientos_mount_alignment_contains_required_mounts() -> None:
    alignment = build_codex_workcell_architecture()["sentientos_mount_alignment"]
    assert {"/vow", "/glow", "/pulse", "/daemon", "/ledger"} <= set(alignment)


def test_future_integration_points_are_not_active_authority() -> None:
    architecture = build_codex_workcell_architecture()
    for point in architecture["future_integration_points"]:
        assert point["status"] == "future_integration"
        assert point["authority_posture"] in {"review_only", "archival_surface"}
        assert point["authority_posture"] != "transition_authority"


def test_output_json_is_deterministic_for_same_inputs() -> None:
    first = json.dumps(build_codex_workcell_architecture(), sort_keys=True)
    second = json.dumps(build_codex_workcell_architecture(), sort_keys=True)
    assert first == second


def test_markdown_output_is_deterministic() -> None:
    first = render_codex_workcell_architecture_markdown()
    second = render_codex_workcell_architecture_markdown()
    assert first == second
    assert first.startswith("# Codex Workcell Architecture")


def test_non_authority_posture_fields_are_present_and_true() -> None:
    posture = build_codex_workcell_architecture()["non_authority_posture"]
    assert REQUIRED_NON_AUTHORITY <= set(posture)
    assert all(posture[key] is True for key in REQUIRED_NON_AUTHORITY)


def test_top_level_non_authority_flags_are_true() -> None:
    architecture = build_codex_workcell_architecture()
    for key in ["metadata_only", "architecture_only", "developer_workflow_evidence_only", "not_runtime_authority", "not_scheduler", "not_executor", "not_model_training", "not_reinforcement_learning"]:
        assert architecture[key] is True
