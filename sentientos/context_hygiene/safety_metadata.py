from __future__ import annotations

from typing import Any, Mapping

from sentientos.context_hygiene.source_kind_contracts import explain_context_safety_contract_gap, validate_context_safety_metadata_against_source_kind


CONTEXT_SAFETY_METADATA_KEY = "context_safety_metadata"

_ALLOWED_KEYS = frozenset(
    {
        "source_kind",
        "privacy_posture",
        "sanitized_context_summary",
        "context_eligible",
        "non_authoritative",
        "decision_power",
        "pollution_risk",
        "provenance_status",
        "contradiction_status",
        "freshness_status",
        "risk_flags",
        "safety_flags",
        "privacy_sensitive",
        "biometric_or_emotion_sensitive",
        "raw_retention_sensitive",
        "raw_perception",
        "raw_embodiment",
        "action_capable",
        "memory_write_capable",
        "feedback_trigger_capable",
        "retention_commit_capable",
        "admit_work_capable",
        "route_work_capable",
        "approve_work_capable",
        "execute_work_capable",
        "fulfill_work_capable",
        "validation_is_not_memory_write",
        "validation_is_not_action_trigger",
        "validation_is_not_retention_commit",
        "handoff_is_not_fulfillment",
        "bridge_is_not_admission",
        "fulfillment_candidate_is_not_effect",
        "fulfillment_receipt_is_not_effect",
        "receipt_does_not_prove_side_effect",
        "preflight_relevant_metadata_present",
        "allow_context_privacy_sensitive",
        "allow_context_biometric_or_emotion",
        "allow_context_raw_retention",
        "source_kind_contract_valid",
        "missing_required_safety_fields",
        "source_kind_contract_gap_reasons",
    }
)


def normalize_context_safety_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in _ALLOWED_KEYS:
        if key in metadata:
            out[key] = metadata[key]
    if "risk_flags" in out and not isinstance(out["risk_flags"], (list, tuple)):
        out["risk_flags"] = [str(out["risk_flags"])]
    if "safety_flags" in out and not isinstance(out["safety_flags"], (list, tuple)):
        out["safety_flags"] = [str(out["safety_flags"])]
    if out:
        out["preflight_relevant_metadata_present"] = True
        valid, reasons = validate_context_safety_metadata_against_source_kind(out)
        out["source_kind_contract_valid"] = valid
        if reasons:
            out["missing_required_safety_fields"] = [r for r in reasons if r.startswith("missing required") or "requires " in r]
            out["source_kind_contract_gap_reasons"] = list(reasons)
    return out


def extract_context_safety_metadata(candidate: Any) -> dict[str, Any]:
    metadata = dict(getattr(candidate, "metadata", {}) or {})
    out = normalize_context_safety_metadata(metadata)
    for key in ("source_kind", "privacy_posture", "sanitized_context_summary", "context_eligible", "non_authoritative", "decision_power"):
        if key not in out and key in metadata:
            out[key] = metadata[key]
    return out


def attach_context_safety_metadata_to_packet_ref(provenance: Mapping[str, Any], metadata: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(provenance)
    out[CONTEXT_SAFETY_METADATA_KEY] = normalize_context_safety_metadata(metadata)
    return out


def packet_ref_has_safety_metadata(item: Any) -> bool:
    return bool(getattr(item, "provenance", {}).get(CONTEXT_SAFETY_METADATA_KEY))


def explain_missing_context_safety_metadata(ref_type: str, metadata: Mapping[str, Any]) -> str | None:
    source_kind = str(metadata.get("source_kind", "")).strip().lower()
    if source_kind == "unknown":
        return f"unknown safety metadata source_kind for {ref_type}"
    return explain_context_safety_contract_gap(metadata)


def safety_metadata_has_action_authority(metadata: Mapping[str, Any]) -> bool:
    return any(
        bool(metadata.get(k, False))
        for k in (
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
    )


def safety_metadata_has_privacy_block(metadata: Mapping[str, Any]) -> bool:
    posture = str(metadata.get("privacy_posture", "public")).lower()
    sensitive = posture in {"privacy_sensitive", "biometric_or_emotion_sensitive", "raw_retention_sensitive"}
    return sensitive and not bool(metadata.get("sanitized_context_summary", False))


def safety_metadata_has_raw_source_block(metadata: Mapping[str, Any]) -> bool:
    return bool(metadata.get("raw_perception", False) or metadata.get("raw_embodiment", False))


def safety_metadata_has_authority_block(metadata: Mapping[str, Any]) -> bool:
    return (not bool(metadata.get("non_authoritative", True))) or str(metadata.get("decision_power", "none")) != "none"
