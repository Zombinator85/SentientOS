"""Bounded authority-of-judgment jurisprudence for currently explicit classes.

This module is intentionally compact. It documents implemented class-local
authority rules and the unresolved classes that remain outside explicit
reconciliation in this pass.
"""

from __future__ import annotations

from typing import Final


EXPLICIT_AUTHORITY_RULES: Final[tuple[dict[str, object], ...]] = (
    {
        "decision_class": "federated_control_admission",
        "authoritative_surface": "runtime_governor",
        "advisory_surfaces": ("request_metadata.federated_denial_cause",),
        "disagreement_class": "runtime_allow_vs_metadata_denial",
        "reconciliation_rule": "runtime_governor_authoritative_for_federated_control",
        "scope_boundary": "ControlPlaneKernel federated_control admission only",
    },
    {
        "decision_class": "maintenance_admission_proof_budget",
        "authoritative_surface": "proof_budget_governor.mode",
        "advisory_surfaces": ("runtime_governor.allowed",),
        "disagreement_class": "runtime_allow_vs_proof_budget_diagnostics_only",
        "reconciliation_rule": "proof_budget_diagnostics_only_authoritative_for_maintenance_admission",
        "scope_boundary": "ControlPlaneKernel maintenance admission classes only",
    },
    {
        "decision_class": "merge_train_mergeability_protected_mutation",
        "authoritative_surface": "protected_corridor.corridor_relevance.protected_mutation_proof_status",
        "advisory_surfaces": (
            "stability_doctrine_and_contract_status",
            "protected_corridor.corridor_relevance",
            "protected_corridor.global_summary.trust_degradation_ledger",
        ),
        "disagreement_class": "strict_corridor_failure_vs_body_scale_status",
        "reconciliation_rule": "strict_corridor_failure_authoritative_when_corridor_intersects",
        "scope_boundary": "ForgeMergeTrain mergeability/automerge hold only",
    },
)


UNRESOLVED_DECISION_CLASSES: Final[tuple[str, ...]] = (
    "repair_admission_cross_surface_precedence",
    "daemon_restart_cross_surface_precedence",
    "global_runtime_vs_merge_train_precedence",
)


IMPLEMENTATION_NOTE: Final[str] = (
    "Authority-of-judgment rules are class-local reconciliations. "
    "They do not define universal precedence across unrelated decision classes. "
    "To add a new rule, add a new class-local emitter and tests without changing "
    "existing class boundaries."
)
