from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


NON_EFFECT_GUARD_FLAGS = (
    "validation_is_not_memory_write",
    "validation_is_not_action_trigger",
    "validation_is_not_retention_commit",
    "handoff_is_not_fulfillment",
    "bridge_is_not_admission",
    "fulfillment_candidate_is_not_effect",
    "fulfillment_receipt_is_not_effect",
    "receipt_does_not_prove_side_effect",
)

CAPABILITY_FLAGS = (
    "action_capable",
    "memory_write_capable",
    "feedback_trigger_capable",
    "retention_commit_capable",
    "admit_work_capable",
    "route_work_capable",
    "approve_work_capable",
    "execute_work_capable",
    "fulfill_work_capable",
)


@dataclass(frozen=True)
class ContextSourceKindSafetyContract:
    source_kind: str
    required_fields: tuple[str, ...] = ()
    optional_fields: tuple[str, ...] = ()
    forbidden_fields: tuple[str, ...] = ()
    requires_scope: bool = False
    requires_provenance: bool = False
    requires_sanitized_summary: bool = False
    requires_privacy_posture: bool = False
    requires_non_authoritative: bool = True
    requires_decision_power_none: bool = True
    requires_context_eligible: bool = False
    requires_non_effect_guard_flags: tuple[str, ...] = ()
    allows_prompt_preflight: bool = True
    fail_closed_if_missing: bool = False
    rationale: str = ""


_CONTRACTS = {
    "unknown": ContextSourceKindSafetyContract("unknown", required_fields=("source_kind",), allows_prompt_preflight=False, fail_closed_if_missing=True),
    "raw_perception_event": ContextSourceKindSafetyContract("raw_perception_event", required_fields=("source_kind",), forbidden_fields=("sanitized_context_summary",), allows_prompt_preflight=False, fail_closed_if_missing=True),
    **{k: ContextSourceKindSafetyContract(k, required_fields=("source_kind",), allows_prompt_preflight=False, fail_closed_if_missing=True) for k in (
        "legacy_screen_artifact", "legacy_audio_artifact", "legacy_vision_artifact", "legacy_multimodal_artifact", "legacy_feedback_artifact")},
    "embodiment_snapshot": ContextSourceKindSafetyContract("embodiment_snapshot", required_fields=("source_kind", "sanitized_context_summary", "privacy_posture", "non_authoritative", "decision_power"), requires_scope=True, requires_provenance=True, requires_sanitized_summary=True, requires_privacy_posture=True),
    "embodiment_ingress_receipt": ContextSourceKindSafetyContract("embodiment_ingress_receipt", required_fields=("source_kind", "non_authoritative", "decision_power"), requires_scope=True, requires_provenance=True),
    "embodiment_proposal": ContextSourceKindSafetyContract("embodiment_proposal", required_fields=("source_kind", "privacy_posture", "non_authoritative", "decision_power"), requires_scope=True, requires_provenance=True, requires_privacy_posture=True),
    "embodiment_proposal_diagnostic": ContextSourceKindSafetyContract("embodiment_proposal_diagnostic", required_fields=("source_kind", "non_authoritative", "decision_power"), requires_scope=True, requires_provenance=True),
    "embodiment_review_receipt": ContextSourceKindSafetyContract("embodiment_review_receipt", required_fields=("source_kind", "non_authoritative", "decision_power"), requires_scope=True, requires_provenance=True),
    "embodiment_handoff_candidate": ContextSourceKindSafetyContract("embodiment_handoff_candidate", required_fields=("source_kind", "handoff_is_not_fulfillment", "non_authoritative", "decision_power"), requires_scope=True, requires_provenance=True, requires_non_effect_guard_flags=("handoff_is_not_fulfillment",)),
    "embodiment_governance_bridge_candidate": ContextSourceKindSafetyContract("embodiment_governance_bridge_candidate", required_fields=("source_kind", "bridge_is_not_admission", "non_authoritative", "decision_power"), requires_scope=True, requires_provenance=True, requires_non_effect_guard_flags=("bridge_is_not_admission",)),
    "embodiment_fulfillment_candidate": ContextSourceKindSafetyContract("embodiment_fulfillment_candidate", required_fields=("source_kind", "fulfillment_candidate_is_not_effect", "non_authoritative", "decision_power"), requires_scope=True, requires_provenance=True, requires_non_effect_guard_flags=("fulfillment_candidate_is_not_effect",)),
    "embodiment_fulfillment_receipt": ContextSourceKindSafetyContract("embodiment_fulfillment_receipt", required_fields=("source_kind", "fulfillment_receipt_is_not_effect", "receipt_does_not_prove_side_effect", "non_authoritative", "decision_power"), requires_scope=True, requires_provenance=True, requires_non_effect_guard_flags=("fulfillment_receipt_is_not_effect", "receipt_does_not_prove_side_effect")),
    "memory_ingress_validation": ContextSourceKindSafetyContract("memory_ingress_validation", required_fields=("source_kind", "validation_is_not_memory_write", "non_authoritative", "decision_power"), requires_scope=True, requires_provenance=True, requires_non_effect_guard_flags=("validation_is_not_memory_write",)),
    "action_ingress_validation": ContextSourceKindSafetyContract("action_ingress_validation", required_fields=("source_kind", "validation_is_not_action_trigger", "non_authoritative", "decision_power"), requires_scope=True, requires_provenance=True, requires_non_effect_guard_flags=("validation_is_not_action_trigger",)),
    "retention_ingress_validation": ContextSourceKindSafetyContract("retention_ingress_validation", required_fields=("source_kind", "validation_is_not_retention_commit", "non_authoritative", "decision_power"), requires_scope=True, requires_provenance=True, requires_non_effect_guard_flags=("validation_is_not_retention_commit",)),
    "diagnostic": ContextSourceKindSafetyContract("diagnostic", required_fields=("source_kind", "non_authoritative", "decision_power"), requires_provenance=True),
    "evidence": ContextSourceKindSafetyContract("evidence", required_fields=("source_kind",), requires_provenance=True, fail_closed_if_missing=False),
    "truth": ContextSourceKindSafetyContract("truth", required_fields=("source_kind",), requires_provenance=True, fail_closed_if_missing=False),
    "research": ContextSourceKindSafetyContract("research", required_fields=("source_kind",), requires_provenance=True, fail_closed_if_missing=False),
}


def get_context_source_kind_safety_contract(source_kind: str | None) -> ContextSourceKindSafetyContract:
    return _CONTRACTS.get(str(source_kind or "").strip().lower(), _CONTRACTS["unknown"])


def context_source_kind_requires_safety_metadata(source_kind: str | None) -> bool:
    k = str(source_kind or "").strip().lower()
    return bool(k and k in _CONTRACTS and k not in {"evidence", "truth", "research"})


def validate_context_safety_metadata_against_source_kind(metadata: Mapping[str, Any]) -> tuple[bool, tuple[str, ...]]:
    m = dict(metadata)
    kind = str(m.get("source_kind", "")).strip().lower()
    if not kind:
        return True, tuple()
    c = get_context_source_kind_safety_contract(kind)
    reasons: list[str] = []
    if kind == "unknown": reasons.append("source_kind unknown")
    for f in c.required_fields:
        if f not in m: reasons.append(f"missing required field: {f}")
    if c.requires_sanitized_summary and not bool(m.get("sanitized_context_summary", False)): reasons.append("missing required field: sanitized_context_summary")
    if c.requires_privacy_posture and not m.get("privacy_posture"): reasons.append("missing required field: privacy_posture")
    if c.requires_non_authoritative and not bool(m.get("non_authoritative", False)): reasons.append("non_authoritative must be true")
    if c.requires_decision_power_none and str(m.get("decision_power", "none")) != "none": reasons.append("decision_power must be none")
    if kind == "embodiment_ingress_receipt" and not (bool(m.get("context_eligible")) or bool(m.get("sanitized_context_summary"))): reasons.append("requires context_eligible or sanitized_context_summary")
    if kind == "embodiment_proposal" and not (bool(m.get("context_eligible")) or bool(m.get("sanitized_context_summary"))): reasons.append("requires context_eligible or sanitized_context_summary")
    if kind == "raw_perception_event" and m.get("raw_perception") is False: reasons.append("raw_perception_event requires raw_perception=true when present")
    for guard in c.requires_non_effect_guard_flags:
        if not bool(m.get(guard, False)): reasons.append(f"missing required guard flag: {guard}")
    if kind == "diagnostic" or kind.startswith("embodiment_"):
        for cap in CAPABILITY_FLAGS:
            if bool(m.get(cap, False)): reasons.append(f"forbidden capability flag: {cap}")
    return not reasons, tuple(reasons)


def explain_context_safety_contract_gap(metadata: Mapping[str, Any]) -> str | None:
    valid, reasons = validate_context_safety_metadata_against_source_kind(metadata)
    return None if valid else "; ".join(reasons)


def source_kind_contract_allows_prompt_preflight(metadata: Mapping[str, Any]) -> bool:
    return get_context_source_kind_safety_contract(metadata.get("source_kind")).allows_prompt_preflight


def source_kind_contract_has_required_non_effect_guards(metadata: Mapping[str, Any]) -> bool:
    c = get_context_source_kind_safety_contract(metadata.get("source_kind"))
    return all(bool(metadata.get(flag, False)) for flag in c.requires_non_effect_guard_flags)


def summarize_source_kind_contract_matrix() -> dict[str, dict[str, Any]]:
    return {k: {"required_fields": list(v.required_fields), "allows_prompt_preflight": v.allows_prompt_preflight, "fail_closed_if_missing": v.fail_closed_if_missing} for k, v in _CONTRACTS.items()}
