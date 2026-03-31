from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from codex.proof_budget_governor import GovernorConfig, PressureState
from sentientos.codex_startup_guard import enforce_codex_startup
from sentientos.control_plane_kernel import (
    AdmissionOutcome,
    AuthorityClass,
    ControlActionRequest,
    ControlPlaneKernel,
    LifecyclePhase,
)
from sentientos.runtime_governor import GovernorDecision, PressureSnapshot


@dataclass
class FakeRuntimeGovernor:
    allow: bool = True
    reason: str = "allowed"

    def admit_action(self, action_type: str, actor: str, correlation_id: str, metadata=None) -> GovernorDecision:
        return GovernorDecision(
            action_class=action_type,
            allowed=self.allow,
            mode="enforce",
            reason=self.reason,
            subject=str((metadata or {}).get("subject") or "subject"),
            scope=str((metadata or {}).get("scope") or "local"),
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
            action_family="control",
        )


def test_legal_bootstrap_action_allowed(tmp_path):
    kernel = ControlPlaneKernel(runtime_governor=FakeRuntimeGovernor(), decisions_path=tmp_path / "decisions.jsonl")
    kernel.set_phase(LifecyclePhase.BOOTSTRAP)
    decision = kernel.admit(
        ControlActionRequest(
            action_kind="integrity_guard",
            authority_class=AuthorityClass.PROPOSAL_EVALUATION,
            actor="boot",
            target_subsystem="integrity",
            requested_phase=LifecyclePhase.BOOTSTRAP,
        )
    )
    assert decision.outcome == AdmissionOutcome.ALLOW


def test_illegal_runtime_startup_bound_action_deferred(tmp_path):
    kernel = ControlPlaneKernel(runtime_governor=FakeRuntimeGovernor(), decisions_path=tmp_path / "decisions.jsonl")
    kernel.set_phase(LifecyclePhase.RUNTIME)
    decision = kernel.admit(
        ControlActionRequest(
            action_kind="spec_cycle",
            authority_class=AuthorityClass.SPEC_AMENDMENT,
            actor="runtime",
            target_subsystem="spec_amender",
            requested_phase=LifecyclePhase.RUNTIME,
        )
    )
    assert decision.outcome == AdmissionOutcome.DEFER
    assert "startup_bound_requires_maintenance" in decision.reason_codes


def test_runtime_maintenance_mediation_allows_startup_guarded_invocation(tmp_path):
    kernel = ControlPlaneKernel(runtime_governor=FakeRuntimeGovernor(), decisions_path=tmp_path / "decisions.jsonl")
    kernel.set_phase(LifecyclePhase.MAINTENANCE)

    invoked = {"ok": False}

    def _invoke() -> bool:
        enforce_codex_startup("GenesisForge")
        invoked["ok"] = True
        return True

    decision, result = kernel.admit_and_execute(
        ControlActionRequest(
            action_kind="expand",
            authority_class=AuthorityClass.PROPOSAL_EVALUATION,
            actor="maintenance",
            target_subsystem="genesis",
            requested_phase=LifecyclePhase.MAINTENANCE,
            startup_symbol="GenesisForge",
        ),
        execute=_invoke,
    )
    assert decision.outcome == AdmissionOutcome.ALLOW
    assert result is True
    assert invoked["ok"] is True


def test_runtime_governor_denial_bubbles_to_kernel(tmp_path):
    kernel = ControlPlaneKernel(
        runtime_governor=FakeRuntimeGovernor(allow=False, reason="restart_budget_exceeded"),
        decisions_path=tmp_path / "decisions.jsonl",
    )
    decision = kernel.admit(
        ControlActionRequest(
            action_kind="restart_daemon",
            authority_class=AuthorityClass.DAEMON_RESTART,
            actor="healer",
            target_subsystem="daemon-x",
            requested_phase=LifecyclePhase.RUNTIME,
            metadata={"subject": "daemon-x"},
        )
    )
    assert decision.outcome == AdmissionOutcome.DENY
    assert "runtime_governor:restart_budget_exceeded" in decision.reason_codes


def test_federated_control_denial(tmp_path):
    kernel = ControlPlaneKernel(runtime_governor=FakeRuntimeGovernor(), decisions_path=tmp_path / "decisions.jsonl")
    decision = kernel.admit(
        ControlActionRequest(
            action_kind="federated_control",
            authority_class=AuthorityClass.FEDERATED_CONTROL,
            actor="peer-a",
            target_subsystem="daemon-y",
            requested_phase=LifecyclePhase.RUNTIME,
            federation_origin="peer-a",
            metadata={"federated_denial_cause": "digest_mismatch", "subject": "daemon-y", "scope": "federated"},
        )
    )
    assert decision.outcome == AdmissionOutcome.DENY
    assert "federation_governance:digest_mismatch" in decision.reason_codes


def test_proof_budget_diagnostics_mode_defers(tmp_path):
    kernel = ControlPlaneKernel(runtime_governor=FakeRuntimeGovernor(), decisions_path=tmp_path / "decisions.jsonl")
    decision = kernel.admit(
        ControlActionRequest(
            action_kind="proposal_eval",
            authority_class=AuthorityClass.PROPOSAL_EVALUATION,
            actor="forge",
            target_subsystem="capability-z",
            requested_phase=LifecyclePhase.RUNTIME,
            metadata={"require_admissible": True},
            proof_budget_context={
                "config": GovernorConfig(
                    configured_k=3,
                    configured_m=2,
                    max_k=9,
                    escalation_enabled=True,
                    mode="diagnostics_only",
                    admissible_collapse_runs=2,
                    min_m=1,
                    diagnostics_k=4,
                ),
                "pressure_state": PressureState(consecutive_no_admissible=0, recent_runs=[]),
                "run_context": {"pipeline": "genesis", "capability": "capability-z", "router_attempt": 1},
            },
        )
    )
    assert decision.outcome == AdmissionOutcome.DEFER
    assert "proof_budget:diagnostics_only" in decision.reason_codes
