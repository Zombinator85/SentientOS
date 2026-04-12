from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from sentientos.constitutional_slice_pattern import non_sovereign_diagnostic_boundaries

_WORK_CLASSES = {
    "internal_runtime_maintenance",
    "bounded_repo_implementation",
    "architectural_audit",
    "cross_slice_consolidation",
    "external_tool_orchestration",
    "operator_required",
}

_VENUES = {
    "internal_direct_execution",
    "codex_implementation",
    "deep_research_audit",
    "operator_decision_required",
    "insufficient_context",
}

_POSTURES = {"expand", "consolidate", "audit", "hold", "escalate"}

_CONSOLIDATION_VS_EXPANSION = {
    "expansion_currently_favored",
    "consolidation_currently_favored",
    "audit_currently_favored",
    "insufficient_context",
    "operator_required",
}

_ESCALATIONS = {
    "no_escalation_needed",
    "escalate_for_operator_priority",
    "escalate_for_missing_context",
    "escalate_for_unmodeled_external_action",
    "escalate_for_governance_ambiguity",
}

_READINESS = {
    "absent",
    "partial",
    "bounded_supervised",
    "nearly_ready",
    "not_ready_for_delegation",
}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _bounded_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _signal_basis(*, evidence: Mapping[str, Any], reasons: list[str]) -> dict[str, Any]:
    return {
        "signal_reasons": reasons,
        "slice_health_status": evidence.get("slice_health_status"),
        "slice_stability_classification": evidence.get("slice_stability_classification"),
        "slice_review_classification": evidence.get("slice_review_classification"),
        "contract_drifted_domains": evidence.get("contract_drifted_domains"),
        "contract_baseline_missing_domains": evidence.get("contract_baseline_missing_domains"),
        "admission_denied_ratio": evidence.get("admission_denied_ratio"),
        "executor_failure_ratio": evidence.get("executor_failure_ratio"),
        "adapter_count": evidence.get("adapter_count"),
        "records_considered": evidence.get("records_considered"),
    }


def collect_delegated_judgment_evidence(
    repo_root: Path,
    *,
    scoped_lifecycle: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    root = repo_root.resolve()
    contract_status = _read_json(root / "glow/contracts/contract_status.json")
    admission_rows = _read_jsonl(root / "logs/task_admission.jsonl")[-120:]
    executor_rows = _read_jsonl(root / "logs/task_executor.jsonl")[-120:]

    contracts = contract_status.get("contracts")
    contract_rows = contracts if isinstance(contracts, list) else []
    drifted_domains = 0
    baseline_missing_domains = 0
    governance_ambiguity = False
    for row in contract_rows:
        if not isinstance(row, Mapping):
            continue
        if row.get("drifted") is True:
            drifted_domains += 1
        drift_type = str(row.get("drift_type") or "")
        if drift_type in {"baseline_missing", "artifact_missing", "preflight_required"}:
            baseline_missing_domains += 1
        domain_name = str(row.get("domain_name") or "")
        if domain_name == "authority_of_judgment_jurisprudence" and (row.get("drifted") is True or drift_type in {"baseline_missing", "artifact_missing"}):
            governance_ambiguity = True

    admission_total = len(admission_rows)
    admission_denied = sum(1 for row in admission_rows if str(row.get("event") or "") == "TASK_ADMISSION_DENIED")
    executor_terminal = [
        row for row in executor_rows if str(row.get("event") or "") == "task_result"
    ]
    executor_terminal_total = len(executor_terminal)
    executor_failed = sum(1 for row in executor_terminal if str(row.get("status") or "") == "failed")

    scoped = scoped_lifecycle or {}
    slice_health = scoped.get("slice_health") if isinstance(scoped.get("slice_health"), Mapping) else {}
    slice_stability = scoped.get("slice_stability") if isinstance(scoped.get("slice_stability"), Mapping) else {}
    retrospective = scoped.get("slice_retrospective_integrity_review") if isinstance(scoped.get("slice_retrospective_integrity_review"), Mapping) else {}

    return {
        "contract_status_present": bool(contract_rows),
        "contract_drifted_domains": drifted_domains,
        "contract_baseline_missing_domains": baseline_missing_domains,
        "governance_ambiguity_signal": governance_ambiguity,
        "slice_health_status": str(slice_health.get("slice_health_status") or "unknown"),
        "slice_stability_classification": str(slice_stability.get("stability_classification") or "insufficient_history"),
        "slice_review_classification": str(retrospective.get("review_classification") or "insufficient_history"),
        "records_considered": int(retrospective.get("records_considered") or 0),
        "admission_denied_ratio": _bounded_ratio(admission_denied, admission_total),
        "admission_sample_count": admission_total,
        "executor_failure_ratio": _bounded_ratio(executor_failed, executor_terminal_total),
        "executor_sample_count": executor_terminal_total,
        "adapter_count": len(_read_jsonl(root / "logs/federation_handshake.jsonl")),
    }


def synthesize_delegated_judgment(
    evidence: Mapping[str, Any],
    *,
    requested_work_hint: str | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []

    slice_health_status = str(evidence.get("slice_health_status") or "unknown")
    stability = str(evidence.get("slice_stability_classification") or "insufficient_history")
    retrospective = str(evidence.get("slice_review_classification") or "insufficient_history")
    records_considered = int(evidence.get("records_considered") or 0)
    contract_drifted = int(evidence.get("contract_drifted_domains") or 0)
    baseline_missing = int(evidence.get("contract_baseline_missing_domains") or 0)
    governance_ambiguity = bool(evidence.get("governance_ambiguity_signal"))
    denied_ratio = float(evidence.get("admission_denied_ratio") or 0.0)
    denied_samples = int(evidence.get("admission_sample_count") or 0)
    failure_ratio = float(evidence.get("executor_failure_ratio") or 0.0)
    failure_samples = int(evidence.get("executor_sample_count") or 0)
    adapter_count = int(evidence.get("adapter_count") or 0)

    insufficient_context = records_considered < 3 and contract_drifted == 0 and baseline_missing == 0
    denied_heavy = denied_samples >= 4 and denied_ratio >= 0.5
    failure_heavy = failure_samples >= 4 and failure_ratio >= 0.35
    fragmentation_heavy = slice_health_status == "fragmented" or retrospective in {"fragmentation_heavy", "oscillatory_instability", "mixed_stress_pattern"}

    if insufficient_context:
        reasons.append("insufficient_recent_evidence")
    if denied_heavy:
        reasons.append("admission_denied_heavy_pattern")
    if failure_heavy:
        reasons.append("executor_failure_heavy_pattern")
    if fragmentation_heavy:
        reasons.append("cross_slice_fragmentation_or_oscillation")
    if governance_ambiguity:
        reasons.append("authority_of_judgment_governance_ambiguity")
    if baseline_missing > 0:
        reasons.append("contract_baseline_missing")
    if contract_drifted > 0:
        reasons.append("contract_drift_present")

    work_class = "bounded_repo_implementation"
    if requested_work_hint == "external_tool_orchestration":
        work_class = "external_tool_orchestration"
    elif governance_ambiguity:
        work_class = "architectural_audit"
    elif fragmentation_heavy:
        work_class = "cross_slice_consolidation"
    elif denied_heavy or failure_heavy:
        work_class = "internal_runtime_maintenance"
    elif insufficient_context:
        work_class = "operator_required"

    venue = "codex_implementation"
    if work_class == "external_tool_orchestration" and adapter_count <= 0:
        venue = "operator_decision_required"
    elif work_class == "operator_required":
        venue = "operator_decision_required"
    elif work_class in {"architectural_audit", "cross_slice_consolidation"}:
        venue = "deep_research_audit"
    elif work_class == "internal_runtime_maintenance":
        venue = "internal_direct_execution"

    posture = "expand"
    consolidation_vs_expansion = "expansion_currently_favored"
    if work_class == "operator_required":
        posture = "escalate"
        consolidation_vs_expansion = "operator_required"
    elif work_class == "architectural_audit":
        posture = "audit"
        consolidation_vs_expansion = "audit_currently_favored"
    elif work_class == "cross_slice_consolidation":
        posture = "consolidate"
        consolidation_vs_expansion = "consolidation_currently_favored"
    elif work_class == "internal_runtime_maintenance":
        posture = "hold"
        consolidation_vs_expansion = "consolidation_currently_favored"

    escalation = "no_escalation_needed"
    if governance_ambiguity:
        escalation = "escalate_for_governance_ambiguity"
    elif insufficient_context:
        escalation = "escalate_for_missing_context"
    elif work_class == "external_tool_orchestration" and adapter_count <= 0:
        escalation = "escalate_for_unmodeled_external_action"

    transport_readiness = "partial"
    delegated_readiness = "not_ready_for_delegation"
    if records_considered <= 0:
        transport_readiness = "absent"
    elif slice_health_status == "healthy" and stability in {"stable", "improving"} and not denied_heavy and not failure_heavy:
        transport_readiness = "bounded_supervised"
        if not governance_ambiguity and not fragmentation_heavy and contract_drifted == 0:
            delegated_readiness = "partial"
    if transport_readiness == "bounded_supervised" and retrospective == "clean_recent_history" and records_considered >= 6 and venue == "codex_implementation":
        transport_readiness = "nearly_ready"
        delegated_readiness = "bounded_supervised"
    if insufficient_context:
        delegated_readiness = "not_ready_for_delegation"

    confidence = "medium"
    if insufficient_context or governance_ambiguity:
        confidence = "low"
    elif records_considered >= 6 and retrospective == "clean_recent_history" and contract_drifted == 0 and baseline_missing == 0:
        confidence = "high"

    if work_class not in _WORK_CLASSES:
        work_class = "operator_required"
    if venue not in _VENUES:
        venue = "insufficient_context"
    if posture not in _POSTURES:
        posture = "hold"
    if consolidation_vs_expansion not in _CONSOLIDATION_VS_EXPANSION:
        consolidation_vs_expansion = "insufficient_context"
    if escalation not in _ESCALATIONS:
        escalation = "escalate_for_missing_context"
    if transport_readiness not in _READINESS:
        transport_readiness = "absent"
    if delegated_readiness not in _READINESS:
        delegated_readiness = "not_ready_for_delegation"

    return {
        "scope": "constitutional_execution_fabric_delegated_judgment",
        "organ": "delegated_judgment_fabric",
        "recommendation_kind": "execution_venue_recommendation",
        "work_class": work_class,
        "recommended_venue": venue,
        "next_move_posture": posture,
        "consolidation_expansion_posture": consolidation_vs_expansion,
        "escalation_classification": escalation,
        "confidence": confidence,
        "basis": _signal_basis(evidence=evidence, reasons=reasons),
        "orchestration_substitution_readiness": {
            "transport_automation_readiness": transport_readiness,
            "delegated_judgment_readiness": delegated_readiness,
        },
        "allowed_vocab": {
            "work_class": sorted(_WORK_CLASSES),
            "recommended_venue": sorted(_VENUES),
            "next_move_posture": sorted(_POSTURES),
            "consolidation_expansion_posture": sorted(_CONSOLIDATION_VS_EXPANSION),
            "escalation_classification": sorted(_ESCALATIONS),
            "readiness_values": sorted(_READINESS),
        },
        "recommendation_only": True,
        "does_not_execute_tools": True,
        "does_not_override_existing_admission": True,
        "does_not_override_kernel_or_governor": True,
        "does_not_select_goals": True,
        "does_not_replace_operator_authority": True,
        **non_sovereign_diagnostic_boundaries(
            derived_from=[
                "contract_status_rollup",
                "scoped_slice_health",
                "scoped_slice_stability",
                "scoped_slice_retrospective_integrity_review",
                "task_admission_log_summary",
                "task_executor_log_summary",
            ]
        ),
    }
