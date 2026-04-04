from __future__ import annotations

from typing import Any

from sentientos import bounded_jurisprudence


EMITTED_DECISION_PATHS: tuple[dict[str, Any], ...] = (
    {
        "decision_class": "federated_control_admission",
        "emitted_from": "ControlPlaneKernel._authority_rule_for_federated_control",
        "persisted_path": "glow/control_plane/kernel_decisions.jsonl delegated_outcomes.authority_of_judgment",
        "surfaced_path": "kernel admission provenance + operator diagnostics",
    },
    {
        "decision_class": "maintenance_admission_proof_budget",
        "emitted_from": "ControlPlaneKernel._authority_rule_for_maintenance_proof_budget",
        "persisted_path": "glow/control_plane/kernel_decisions.jsonl delegated_outcomes.authority_of_judgment",
        "surfaced_path": "kernel admission provenance + operator diagnostics",
    },
    {
        "decision_class": "merge_train_mergeability_protected_mutation",
        "emitted_from": "ForgeMergeTrain._mergeability_authority_of_judgment",
        "persisted_path": "merge-train hold docket + merge receipt mergeability_authority",
        "surfaced_path": "merge-train/report surfaces",
    },
)


def build_jurisprudence_consumption_summary(*, consumer_surface: str) -> dict[str, Any]:
    explicit = {
        str(item.get("decision_class")): item
        for item in bounded_jurisprudence.EXPLICIT_AUTHORITY_RULES
        if isinstance(item, dict) and isinstance(item.get("decision_class"), str)
    }
    unresolved = [str(item) for item in bounded_jurisprudence.UNRESOLVED_DECISION_CLASSES if isinstance(item, str) and item]

    emitted_vs_consumed: list[dict[str, Any]] = []
    mapping_gaps = 0
    for row in EMITTED_DECISION_PATHS:
        decision_class = str(row["decision_class"])
        rule = explicit.get(decision_class)
        has_rule = isinstance(rule, dict)
        if not has_rule:
            mapping_gaps += 1
        emitted_vs_consumed.append(
            {
                "decision_class": decision_class,
                "emitted_from": row["emitted_from"],
                "persisted_path": row["persisted_path"],
                "surfaced_path": row["surfaced_path"],
                "mapped_in_jurisprudence": has_rule,
                "consumer_surface": consumer_surface,
                "consumption_state": "explicit_rule_consumed" if has_rule else "unresolved_no_explicit_rule",
                "authoritative_surface": str(rule.get("authoritative_surface")) if has_rule else None,
                "reconciliation_rule": str(rule.get("reconciliation_rule")) if has_rule else None,
            }
        )

    unresolved_rows = [
        {
            "decision_class": decision_class,
            "consumer_surface": consumer_surface,
            "consumption_state": "unresolved_no_explicit_rule",
        }
        for decision_class in unresolved
    ]

    return {
        "schema_version": 1,
        "consumer_surface": consumer_surface,
        "implementation_note": bounded_jurisprudence.IMPLEMENTATION_NOTE,
        "explicit_rule_count": len(explicit),
        "emitted_class_count": len(EMITTED_DECISION_PATHS),
        "mapping_gap_count": mapping_gaps,
        "has_mapping_gaps": mapping_gaps > 0,
        "emitted_vs_consumed": emitted_vs_consumed,
        "unresolved_classes": unresolved_rows,
    }
