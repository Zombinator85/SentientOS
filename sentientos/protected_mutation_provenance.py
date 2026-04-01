from __future__ import annotations

from typing import Any, Mapping

REQUIRED_ALLOW_FIELDS: tuple[str, ...] = (
    "correlation_id",
    "admission_decision_ref",
    "action_kind",
    "authority_class",
    "lifecycle_phase",
    "final_disposition",
    "execution_owner",
)

REQUIRED_NON_EXECUTION_FIELDS: tuple[str, ...] = (
    "correlation_id",
    "admission_decision_ref",
    "action_kind",
    "authority_class",
    "lifecycle_phase",
    "final_disposition",
)

NON_EXECUTION_DISPOSITIONS = {"deny", "defer", "quarantine"}


def build_admission_provenance(decision: Any) -> dict[str, object]:
    payload: dict[str, object] = {
        "correlation_id": decision.correlation_id,
        "admission_decision_ref": decision.admission_decision_ref,
        "action_kind": decision.action_kind,
        "authority_class": decision.authority_class.value,
        "lifecycle_phase": decision.current_phase.value,
        "final_disposition": decision.outcome.value,
        "delegate_checks_consulted": sorted(decision.delegated_outcomes.keys()),
        "execution_owner": decision.actor,
    }
    validate_admission_provenance(payload, expect_execution=decision.allowed)
    return payload


def validate_admission_provenance(payload: Mapping[str, Any], *, expect_execution: bool) -> None:
    required = REQUIRED_ALLOW_FIELDS if expect_execution else REQUIRED_NON_EXECUTION_FIELDS
    missing = [field for field in required if not str(payload.get(field) or "").strip()]
    if missing:
        raise ValueError(f"missing_required_provenance_fields:{','.join(sorted(missing))}")

    correlation_id = str(payload.get("correlation_id") or "").strip()
    expected_ref = f"kernel_decision:{correlation_id}"
    admission_ref = str(payload.get("admission_decision_ref") or "").strip()
    if admission_ref != expected_ref:
        raise ValueError(f"invalid_admission_decision_ref:{admission_ref}")

    disposition = str(payload.get("final_disposition") or "").strip()
    if expect_execution and disposition != "allow":
        raise ValueError(f"execution_requires_allow_disposition:{disposition}")
    if not expect_execution and disposition not in NON_EXECUTION_DISPOSITIONS:
        raise ValueError(f"non_execution_requires_non_allow_disposition:{disposition}")
