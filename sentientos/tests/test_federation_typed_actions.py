from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sentientos.control_plane_kernel import (
    AuthorityClass,
    ControlActionRequest,
    ControlPlaneKernel,
    LifecyclePhase,
)
from sentientos.federation_typed_actions import (
    FEDERATION_TYPED_ACTION_REGISTRY,
    federation_typed_action_diagnostic,
    resolve_federation_typed_action_id,
    validate_federation_typed_action_registry,
)
from sentientos.runtime_governor import GovernorDecision, PressureSnapshot


@dataclass
class _AllowingGovernor:
    def admit_action(self, action_type: str, actor: str, correlation_id: str, metadata=None) -> GovernorDecision:  # noqa: ANN001
        return GovernorDecision(
            action_class=action_type,
            allowed=True,
            mode="enforce",
            reason="allowed",
            subject=str((metadata or {}).get("subject") or "subject"),
            scope=str((metadata or {}).get("scope") or "federated"),
            origin=actor,
            sampled_pressure=PressureSnapshot(
                cpu=0.1,
                io=0.1,
                thermal=0.1,
                gpu=0.1,
                composite=0.1,
                sampled_at=datetime.now(timezone.utc).isoformat(),
            ),
            reason_hash="hash",
            correlation_id=correlation_id,
            action_priority=0,
            action_family="federated",
        )


def test_bounded_federation_actions_have_stable_ids() -> None:
    assert set(FEDERATION_TYPED_ACTION_REGISTRY.keys()) == {
        "sentientos.federation.restart_daemon_request",
        "sentientos.federation.governance_digest_or_quorum_denial_gate",
        "sentientos.federation.epoch_or_trust_posture_gate",
    }


def test_entry_surface_resolution_emits_expected_typed_action_ids() -> None:
    assert (
        resolve_federation_typed_action_id(payload_action="restart_daemon")
        == "sentientos.federation.restart_daemon_request"
    )
    assert (
        resolve_federation_typed_action_id(denial_cause="quorum_failure")
        == "sentientos.federation.governance_digest_or_quorum_denial_gate"
    )
    assert (
        resolve_federation_typed_action_id(trust_epoch_classification="revoked_epoch")
        == "sentientos.federation.epoch_or_trust_posture_gate"
    )


def test_out_of_scope_federation_paths_are_not_falsely_typed() -> None:
    assert (
        resolve_federation_typed_action_id(
            payload_action="sync_state",
            denial_cause="",
            trust_epoch_classification="trusted",
        )
        is None
    )


def test_invalid_registry_mapping_is_detectable() -> None:
    errors = validate_federation_typed_action_registry(
        {
            "sentientos.federation.restart_daemon_request": {
                "action_id": "sentientos.federation.restart_daemon_request",
                "intent": "",
            }
        }
    )
    assert any(item.startswith("missing_") for item in errors)


def test_typed_identity_does_not_change_admission_behavior(tmp_path) -> None:
    untyped_kernel = ControlPlaneKernel(runtime_governor=_AllowingGovernor(), decisions_path=tmp_path / "kernel_untyped.jsonl")
    typed_kernel = ControlPlaneKernel(runtime_governor=_AllowingGovernor(), decisions_path=tmp_path / "kernel_typed.jsonl")
    base = ControlActionRequest(
        action_kind="federated_control",
        authority_class=AuthorityClass.FEDERATED_CONTROL,
        actor="peer-a",
        target_subsystem="peer-a:federation",
        requested_phase=LifecyclePhase.RUNTIME,
        metadata={"scope": "federated", "subject": "peer-a:federation"},
    )
    typed = ControlActionRequest(
        action_kind=base.action_kind,
        authority_class=base.authority_class,
        actor=base.actor,
        target_subsystem=base.target_subsystem,
        requested_phase=base.requested_phase,
        metadata={
            "scope": "federated",
            "subject": "peer-a:federation",
            "typed_action_id": "sentientos.federation.governance_digest_or_quorum_denial_gate",
        },
    )
    untyped_decision = untyped_kernel.admit(base)
    typed_decision = typed_kernel.admit(typed)
    assert untyped_decision.outcome == typed_decision.outcome
    assert untyped_decision.authority_class == typed_decision.authority_class


def test_diagnostic_surfaces_chosen_and_out_of_scope_sets() -> None:
    diagnostic = federation_typed_action_diagnostic()
    assert diagnostic["typed_identity_status"] == "bounded_initial_registration"
    assert len(diagnostic["chosen_intents"]) == 3
    assert diagnostic["untyped_out_of_scope_intents"]
