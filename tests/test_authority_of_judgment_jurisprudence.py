from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from sentientos.bounded_jurisprudence import EXPLICIT_AUTHORITY_RULES, UNRESOLVED_DECISION_CLASSES
from sentientos.control_plane_kernel import ControlPlaneKernel
from sentientos.forge_merge_train import _mergeability_authority_of_judgment
from sentientos.runtime_governor import GovernorDecision, PressureSnapshot


def _runtime_allowed_decision() -> GovernorDecision:
    return GovernorDecision(
        action_class="federated_control",
        allowed=True,
        mode="enforce",
        reason="allowed",
        subject="node-a",
        scope="federated",
        origin="peer-a",
        sampled_pressure=PressureSnapshot(
            cpu=0.1,
            io=0.1,
            thermal=0.1,
            gpu=0.1,
            composite=0.1,
            sampled_at=datetime.now(timezone.utc).isoformat(),
        ),
        reason_hash="hash",
        correlation_id="cid",
        action_priority=0,
        action_family="federated",
    )


def test_authority_schema_is_consistent_across_explicit_rule_set() -> None:
    federated = ControlPlaneKernel._authority_rule_for_federated_control(
        runtime=_runtime_allowed_decision(),
        advisory_denial="digest_mismatch",
    )
    maintenance = ControlPlaneKernel._authority_rule_for_maintenance_proof_budget(
        runtime=_runtime_allowed_decision(),
        budget_decision=SimpleNamespace(mode="diagnostics_only"),
    )
    mergeability = _mergeability_authority_of_judgment(
        body_scale_failures=[],
        corridor_signal={"present": True, "intersects_corridor": True, "protected_mutation_proof_status": "strict_violation_present"},
        strict_corridor_failure=True,
    )
    payloads = [federated, maintenance, mergeability]

    required_keys = {
        "decision_class",
        "authoritative_surface",
        "advisory_surfaces",
        "disagreement_present",
        "reconciliation_rule",
        "authority_of_judgment",
        "reconciliation",
    }
    for payload in payloads:
        assert required_keys.issubset(set(payload))
        assert payload["disagreement_present"] == payload["surface_disagreement"]
        assert payload["reconciliation_rule"] == payload["reconciliation"]["rule"]

    classes = {payload["decision_class"] for payload in payloads}
    assert classes == {row["decision_class"] for row in EXPLICIT_AUTHORITY_RULES}


def test_bounded_jurisprudence_remains_class_local() -> None:
    assert "repair_admission_cross_surface_precedence" in UNRESOLVED_DECISION_CLASSES
    assert "daemon_restart_cross_surface_precedence" in UNRESOLVED_DECISION_CLASSES
    assert "global_runtime_vs_merge_train_precedence" in UNRESOLVED_DECISION_CLASSES
