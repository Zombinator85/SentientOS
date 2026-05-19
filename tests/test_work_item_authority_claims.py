from __future__ import annotations

from dataclasses import asdict
from typing import Any

from sentientos.work_item_authority_claims import (
    ALIASES_TO_FAMILY,
    AUTHORITY_CLAIM_ALIASES,
    CANONICAL_AUTHORITY_CLAIM_FAMILIES,
    NON_AUTHORITY_FIELD_ALLOWLIST_VALUES,
    authority_claim_summary,
    authority_claims_from_nested_evidence,
    authority_contradiction_codes,
    normalize_authority_claims,
)
from sentientos.work_item_dry_run_closure import WorkItemDryRunClosureRequest, build_work_item_dry_run_closure_manifest
from sentientos.work_item_intake import normalize_work_item_intake
from sentientos.work_item_lifecycle_dry_run_adapter import WorkItemLifecycleDryRunAdapterRequest, run_work_item_lifecycle_dry_run_adapter
from sentientos.work_item_lifecycle_handoff import WorkItemLifecycleHandoffRequest, plan_work_item_lifecycle_handoff

AUTHORITY_HEURISTIC_TOKENS: tuple[str, ...] = (
    "_requested",
    "_permitted",
    "_performed",
    "_invoked",
    "_used",
    "_claimed",
    "_enabled",
    "_allowed",
    "_created",
    "_mutated",
    "_executed",
    "authority",
    "execution",
    "scheduler",
    "tracker",
    "network",
    "provider",
    "prompt",
    "subprocess",
    "shell",
    "branch",
    "pr_",
    "issue",
    "workspace",
    "target_write",
    "rollback",
    "verification",
    "closure",
)


def _authority_looking_fields(fields: set[str]) -> set[str]:
    return {f for f in fields if any(token in f for token in AUTHORITY_HEURISTIC_TOKENS)}


def _unknown_authority_fields(fields: set[str]) -> tuple[str, ...]:
    unknown = sorted(
        field
        for field in _authority_looking_fields(fields)
        if field not in ALIASES_TO_FAMILY and field not in NON_AUTHORITY_FIELD_ALLOWLIST_VALUES
    )
    return tuple(unknown)


def _iter_field_paths(node: Any, *, root: str = ""):
    if isinstance(node, dict):
        for key in sorted(node):
            key_str = str(key)
            path = f"{root}.{key_str}" if root else key_str
            yield key_str, path
            yield from _iter_field_paths(node[key], root=path)
    elif isinstance(node, (list, tuple)):
        for idx, item in enumerate(node):
            path = f"{root}[{idx}]" if root else f"[{idx}]"
            yield from _iter_field_paths(item, root=path)


def _unknown_authority_field_paths(payloads: dict[str, Any]) -> tuple[str, ...]:
    unknown_paths = []
    for label in sorted(payloads):
        for field, path in _iter_field_paths(payloads[label], root=label):
            if (
                any(token in field for token in AUTHORITY_HEURISTIC_TOKENS)
                and field not in ALIASES_TO_FAMILY
                and field not in NON_AUTHORITY_FIELD_ALLOWLIST_VALUES
            ):
                unknown_paths.append(path)
    return tuple(sorted(unknown_paths))


def test_all_families_have_aliases():
    for family in CANONICAL_AUTHORITY_CLAIM_FAMILIES:
        assert family in AUTHORITY_CLAIM_ALIASES
        assert AUTHORITY_CLAIM_ALIASES[family]


def test_aliases_map_to_canonical_family():
    for family, aliases in AUTHORITY_CLAIM_ALIASES.items():
        for alias in aliases:
            assert ALIASES_TO_FAMILY[alias] == family


def test_normalize_boolean_like_and_ambiguous_values():
    claims = normalize_authority_claims(
        {
            "network_requested": "yes",
            "provider_requested": "true",
            "prompt_export_requested": "enabled",
            "subprocess_used": 0,
            "scheduler_requested": 1,
        }
    )
    assert claims["network"] is True
    assert claims["provider"] is True
    assert claims["scheduler"] is True
    assert claims["prompt_export"] is False
    assert claims["subprocess_or_shell"] is False


def test_nested_evidence_extraction_and_deterministic_outputs():
    claims = authority_claims_from_nested_evidence(
        {"packet": {"agent_execution_requested": True}},
        {"handoff": [{"network_performed": "yes"}]},
        {"dry": {"result": {"workspace_execution_performed": True}}},
    )
    summary = authority_claim_summary(claims)
    codes = authority_contradiction_codes(claims)
    assert summary == ("agent_execution", "network", "workspace_execution")
    assert codes == (
        "dry_run_claims_agent_execution_authority",
        "dry_run_claims_network_authority",
        "dry_run_claims_workspace_execution_authority",
    )


def _build_representative_producer_outputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    packet, _ = normalize_work_item_intake(
        {
            "source_kind": "manual_operator_task",
            "source_ref": "WI-123",
            "title": "Add authority vocabulary coverage",
            "description": "metadata only",
            "requested_outcome": "deterministic coverage",
            "declared_targets": ["sentientos/work_item_authority_claims.py"],
            "declared_authority_requests": ["filesystem_write"],
            "agent_execution_requested": False,
        },
        derive_workspace_proposal=True,
    )
    packet_dict = asdict(packet)
    handoff = plan_work_item_lifecycle_handoff(WorkItemLifecycleHandoffRequest(packet=packet_dict, emit_lifecycle_candidate=True))
    dry = run_work_item_lifecycle_dry_run_adapter(
        WorkItemLifecycleDryRunAdapterRequest(
            packet=packet_dict,
            handoff_plan=asdict(handoff),
            workspace_root=None,
            request_dry_run=False,
        )
    )
    closure = build_work_item_dry_run_closure_manifest(
        WorkItemDryRunClosureRequest(packet=packet_dict, handoff_plan=asdict(handoff), dry_run_result=dry.to_dict())
    )
    return packet_dict, asdict(handoff), dry.to_dict(), closure.manifest.to_dict()


def test_producer_authority_like_fields_have_alias_or_non_authority_classification():
    packet_dict, handoff_dict, dry_dict, closure_manifest = _build_representative_producer_outputs()
    observed = set(packet_dict) | set(handoff_dict) | set(dry_dict) | set(closure_manifest)
    assert _unknown_authority_fields(observed) == ()


def test_nested_producer_authority_like_paths_have_alias_or_non_authority_classification():
    packet_dict, handoff_dict, dry_dict, closure_manifest = _build_representative_producer_outputs()
    unknown = _unknown_authority_field_paths(
        {
            "intake_packet": packet_dict,
            "handoff_plan": handoff_dict,
            "dry_run_result": dry_dict,
            "closure_manifest": closure_manifest,
        }
    )
    assert unknown == ()


def test_serialized_artifact_payload_authority_like_paths_have_alias_or_non_authority_classification():
    packet_dict, handoff_dict, dry_dict, closure_manifest = _build_representative_producer_outputs()
    intake_artifact = {"packet": packet_dict}
    handoff_artifact = {"plan": handoff_dict}
    dry_run_artifact = {
        "request": {
            "work_item_id": packet_dict.get("work_item_id"),
            "handoff_plan_id": dry_dict.get("handoff_plan_id"),
            "workspace_root": None,
            "request_dry_run": False,
        },
        "result": {
            "adapter_status": dry_dict.get("adapter_status"),
            "dry_run_eligibility_status": dry_dict.get("dry_run_eligibility_status"),
            "lifecycle_orchestration_invoked": dry_dict.get("lifecycle_orchestration_invoked"),
            "lifecycle_mode_used": dry_dict.get("lifecycle_mode_used"),
            "lifecycle_dry_run_status": dry_dict.get("lifecycle_dry_run_status"),
            "lifecycle_stop_reason": dry_dict.get("lifecycle_stop_reason"),
            "admission_status": dry_dict.get("admission_status"),
            "preflight_status": dry_dict.get("preflight_status"),
            "transaction_plan_status": dry_dict.get("transaction_plan_status"),
            "transaction_plan_ready": dry_dict.get("transaction_plan_ready"),
        },
    }
    closure_artifact = {"manifest": closure_manifest, "artifact_records": []}
    unknown = _unknown_authority_field_paths(
        {
            "intake_packet_artifact": intake_artifact,
            "handoff_plan_artifact": handoff_artifact,
            "dry_run_adapter_artifact": dry_run_artifact,
            "dry_run_closure_manifest_artifact": closure_artifact,
        }
    )
    assert unknown == ()


def test_nested_unknown_authority_looking_field_fails_with_dotted_path():
    unknown = _unknown_authority_field_paths(
        {"dry_run_result": {"lifecycle_summary": {"execution_performed": False, "new_scheduler_enabled": False}}}
    )
    assert unknown == (
        "dry_run_result.lifecycle_summary.new_scheduler_enabled",
    )


def test_nested_known_non_authority_field_passes_with_dotted_path_scan():
    unknown = _unknown_authority_field_paths(
        {"closure_manifest": {"artifacts": [{"artifact_created": True}], "closure_status": "dry_run_closed_clean"}}
    )
    assert unknown == ()


def test_unknown_authority_looking_field_fails_coverage():
    unknown = _unknown_authority_fields({"network_permitted", "new_scheduler_enabled"})
    assert unknown == ("new_scheduler_enabled",)


def test_known_non_authority_field_passes_coverage_allowlist():
    unknown = _unknown_authority_fields({"workspace_change_set_admission_may_be_attempted"})
    assert unknown == ()
