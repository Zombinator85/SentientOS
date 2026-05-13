from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

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


@dataclass
class MissingRuntimeGovernor:
    pass


@dataclass
class ExplodingRuntimeGovernor:
    def admit_action(self, action_type: str, actor: str, correlation_id: str, metadata=None) -> GovernorDecision:
        raise RuntimeError("boom")


@dataclass
class CountingRuntimeGovernor(FakeRuntimeGovernor):
    calls: int = 0

    def admit_action(self, action_type: str, actor: str, correlation_id: str, metadata=None) -> GovernorDecision:
        self.calls += 1
        return super().admit_action(action_type, actor, correlation_id, metadata=metadata)


class MutableClock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _restart_request(correlation_id: str, *, phase: LifecyclePhase = LifecyclePhase.RUNTIME) -> ControlActionRequest:
    return ControlActionRequest(
        action_kind="restart_daemon",
        authority_class=AuthorityClass.DAEMON_RESTART,
        actor="healer",
        target_subsystem="daemon-x",
        requested_phase=phase,
        metadata={"correlation_id": correlation_id, "subject": "daemon-x"},
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


def test_manifest_mutation_requires_maintenance_phase(tmp_path):
    kernel = ControlPlaneKernel(runtime_governor=FakeRuntimeGovernor(), decisions_path=tmp_path / "decisions.jsonl")
    kernel.set_phase(LifecyclePhase.RUNTIME)
    decision = kernel.admit(
        ControlActionRequest(
            action_kind="generate_immutable_manifest",
            authority_class=AuthorityClass.MANIFEST_OR_IDENTITY_MUTATION,
            actor="operator_cli",
            target_subsystem="vow/immutable_manifest.json",
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


def test_runtime_startup_symbol_without_maintenance_mediation_is_deferred(tmp_path):
    kernel = ControlPlaneKernel(runtime_governor=FakeRuntimeGovernor(), decisions_path=tmp_path / "decisions.jsonl")
    kernel.set_phase(LifecyclePhase.RUNTIME)
    decision, result = kernel.admit_and_execute(
        ControlActionRequest(
            action_kind="expand",
            authority_class=AuthorityClass.REPAIR,
            actor="runtime",
            target_subsystem="genesis",
            requested_phase=LifecyclePhase.RUNTIME,
            startup_symbol="GenesisForge",
        ),
        execute=lambda: enforce_codex_startup("GenesisForge"),
    )
    assert decision.outcome == AdmissionOutcome.DEFER
    assert "startup_mediation_required" in decision.reason_codes
    assert result is None


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


def test_missing_runtime_governor_delegate_is_deferred(tmp_path):
    kernel = ControlPlaneKernel(runtime_governor=MissingRuntimeGovernor(), decisions_path=tmp_path / "decisions.jsonl")  # type: ignore[arg-type]
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
    assert decision.outcome == AdmissionOutcome.DEFER
    assert "runtime_governor_unavailable" in decision.reason_codes


def test_runtime_governor_exception_is_deferred(tmp_path):
    kernel = ControlPlaneKernel(runtime_governor=ExplodingRuntimeGovernor(), decisions_path=tmp_path / "decisions.jsonl")  # type: ignore[arg-type]
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
    assert decision.outcome == AdmissionOutcome.DEFER
    assert "runtime_governor_error" in decision.reason_codes


def test_federated_control_metadata_denial_is_advisory_when_runtime_allows(tmp_path):
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
    assert decision.outcome == AdmissionOutcome.ALLOW
    assert "authority_reconciliation:federated_control_runtime_governor_authoritative" in decision.reason_codes
    assert "federation_governance_advisory:digest_mismatch" in decision.reason_codes
    authority = decision.delegated_outcomes.get("authority_of_judgment")
    assert isinstance(authority, dict)
    assert authority.get("authoritative_surface") == "runtime_governor"
    assert authority.get("surface_disagreement") is True
    assert authority.get("disagreement_present") is True
    assert authority.get("reconciliation_rule") == "runtime_governor_authoritative_for_federated_control"
    assert authority.get("authority_of_judgment") == "runtime_governor_is_authoritative_for_federated_control"
    reconciliation = authority.get("reconciliation")
    assert isinstance(reconciliation, dict)
    assert reconciliation.get("state") == "reconciled"
    assert reconciliation.get("rule") == "runtime_governor_authoritative_for_federated_control"


def test_federated_control_missing_origin_is_quarantined(tmp_path):
    kernel = ControlPlaneKernel(runtime_governor=FakeRuntimeGovernor(), decisions_path=tmp_path / "decisions.jsonl")
    decision = kernel.admit(
        ControlActionRequest(
            action_kind="federated_control",
            authority_class=AuthorityClass.FEDERATED_CONTROL,
            actor="peer-a",
            target_subsystem="daemon-y",
            requested_phase=LifecyclePhase.RUNTIME,
            metadata={"subject": "daemon-y", "scope": "federated"},
        )
    )
    assert decision.outcome == AdmissionOutcome.QUARANTINE
    assert "federation_origin_missing" in decision.reason_codes


def test_unresolved_non_federated_governance_ambiguity_is_not_marked_reconciled(tmp_path):
    kernel = ControlPlaneKernel(runtime_governor=FakeRuntimeGovernor(), decisions_path=tmp_path / "decisions.jsonl")
    decision = kernel.admit(
        ControlActionRequest(
            action_kind="restart_daemon",
            authority_class=AuthorityClass.DAEMON_RESTART,
            actor="healer",
            target_subsystem="daemon-x",
            requested_phase=LifecyclePhase.RUNTIME,
            metadata={"federated_denial_cause": "digest_mismatch", "subject": "daemon-x"},
        )
    )
    assert decision.outcome == AdmissionOutcome.ALLOW
    assert decision.delegated_outcomes.get("authority_of_judgment") is None
    assert not any("authority_reconciliation:" in reason for reason in decision.reason_codes)


def test_proof_budget_diagnostics_mode_defers(tmp_path):
    kernel = ControlPlaneKernel(runtime_governor=FakeRuntimeGovernor(), decisions_path=tmp_path / "decisions.jsonl")
    kernel.set_phase(LifecyclePhase.MAINTENANCE)
    decision = kernel.admit(
        ControlActionRequest(
            action_kind="proposal_eval",
            authority_class=AuthorityClass.PROPOSAL_EVALUATION,
            actor="forge",
            target_subsystem="capability-z",
            requested_phase=LifecyclePhase.MAINTENANCE,
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
    assert "authority_reconciliation:maintenance_proof_budget_authoritative" in decision.reason_codes
    authority = decision.delegated_outcomes.get("authority_of_judgment")
    assert isinstance(authority, dict)
    assert authority.get("decision_class") == "maintenance_admission_proof_budget"
    assert authority.get("authoritative_surface") == "proof_budget_governor.mode"
    assert authority.get("surface_disagreement") is True
    assert authority.get("disagreement_present") is True
    assert authority.get("reconciliation_rule") == "proof_budget_diagnostics_only_authoritative_for_maintenance_admission"
    assert authority.get("authority_of_judgment") == "proof_budget_governor_mode_is_authoritative_for_maintenance_admission"
    reconciliation = authority.get("reconciliation")
    assert isinstance(reconciliation, dict)
    assert reconciliation.get("rule") == "proof_budget_diagnostics_only_authoritative_for_maintenance_admission"


def test_maintenance_proof_authority_clears_when_diagnostics_only_clears(tmp_path):
    kernel = ControlPlaneKernel(runtime_governor=FakeRuntimeGovernor(), decisions_path=tmp_path / "decisions.jsonl")
    kernel.set_phase(LifecyclePhase.MAINTENANCE)
    base_context = {
        "pressure_state": PressureState(consecutive_no_admissible=0, recent_runs=[]),
        "run_context": {"pipeline": "genesis", "capability": "capability-z", "router_attempt": 1},
    }
    deferred = kernel.admit(
        ControlActionRequest(
            action_kind="proposal_eval",
            authority_class=AuthorityClass.PROPOSAL_EVALUATION,
            actor="forge",
            target_subsystem="capability-z",
            requested_phase=LifecyclePhase.MAINTENANCE,
            metadata={"require_admissible": True, "correlation_id": "proof-clear-1"},
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
                **base_context,
            },
        )
    )
    assert deferred.outcome == AdmissionOutcome.DEFER
    admitted = kernel.admit(
        ControlActionRequest(
            action_kind="proposal_eval",
            authority_class=AuthorityClass.PROPOSAL_EVALUATION,
            actor="forge",
            target_subsystem="capability-z",
            requested_phase=LifecyclePhase.MAINTENANCE,
            metadata={"require_admissible": True, "correlation_id": "proof-clear-2"},
            proof_budget_context={
                "config": GovernorConfig(
                    configured_k=3,
                    configured_m=2,
                    max_k=9,
                    escalation_enabled=True,
                    mode="normal",
                    admissible_collapse_runs=2,
                    min_m=1,
                    diagnostics_k=4,
                ),
                **base_context,
            },
        )
    )
    assert admitted.outcome == AdmissionOutcome.ALLOW
    authority = admitted.delegated_outcomes.get("authority_of_judgment")
    assert isinstance(authority, dict)
    assert authority.get("decision_class") == "maintenance_admission_proof_budget"
    assert authority.get("surface_disagreement") is False
    assert authority.get("disagreement_present") is False
    assert "proof_budget:diagnostics_only" not in admitted.reason_codes
    assert "authority_reconciliation:maintenance_proof_budget_authoritative" not in admitted.reason_codes


def test_malformed_action_request_is_quarantined(tmp_path):
    kernel = ControlPlaneKernel(runtime_governor=FakeRuntimeGovernor(), decisions_path=tmp_path / "decisions.jsonl")
    decision = kernel.admit(
        ControlActionRequest(
            action_kind=" ",
            authority_class=AuthorityClass.REPAIR,
            actor="runtime",
            target_subsystem="healer",
            requested_phase=LifecyclePhase.RUNTIME,
        )
    )
    assert decision.outcome == AdmissionOutcome.QUARANTINE
    assert "invalid_action_kind" in decision.reason_codes


def test_duplicate_admission_attempt_in_same_phase_is_deferred(tmp_path):
    kernel = ControlPlaneKernel(runtime_governor=FakeRuntimeGovernor(), decisions_path=tmp_path / "decisions.jsonl")
    request = ControlActionRequest(
        action_kind="restart_daemon",
        authority_class=AuthorityClass.DAEMON_RESTART,
        actor="healer",
        target_subsystem="daemon-x",
        requested_phase=LifecyclePhase.RUNTIME,
        metadata={"correlation_id": "dup-1", "subject": "daemon-x"},
    )
    first = kernel.admit(request)
    second = kernel.admit(request)
    assert first.outcome == AdmissionOutcome.ALLOW
    assert second.outcome == AdmissionOutcome.DEFER
    assert "duplicate_admission_context" in second.reason_codes




def test_duplicate_admission_dedupe_status_is_explicit_and_no_duplicate_execution(tmp_path):
    clock = MutableClock(100.0)
    governor = CountingRuntimeGovernor()
    kernel = ControlPlaneKernel(
        runtime_governor=governor,
        decisions_path=tmp_path / "decisions.jsonl",
        admission_dedupe_ttl_seconds=30.0,
        clock=clock,
    )
    executions = {"count": 0}

    def _execute() -> str:
        executions["count"] += 1
        return "executed"

    first, result = kernel.admit_and_execute(_restart_request("dup-exec-1"), execute=_execute)
    second, duplicate_result = kernel.admit_and_execute(_restart_request("dup-exec-1"), execute=_execute)

    assert first.outcome == AdmissionOutcome.ALLOW
    assert result == "executed"
    assert second.outcome == AdmissionOutcome.DEFER
    assert duplicate_result is None
    assert "duplicate_admission_context" in second.reason_codes
    assert second.delegated_outcomes["admission_dedupe"]["key_shape"] == "(current_phase.value, correlation_id)"
    assert second.delegated_outcomes["admission_dedupe"]["scope"] == "process_local"
    assert executions["count"] == 1
    assert governor.calls == 1


def test_dedupe_key_is_phase_and_correlation_id_not_action_shape(tmp_path):
    clock = MutableClock(200.0)
    kernel = ControlPlaneKernel(
        runtime_governor=FakeRuntimeGovernor(),
        decisions_path=tmp_path / "decisions.jsonl",
        admission_dedupe_ttl_seconds=60.0,
        clock=clock,
    )

    first = kernel.admit(_restart_request("shared-corr", phase=LifecyclePhase.RUNTIME))
    other_correlation = kernel.admit(_restart_request("other-corr", phase=LifecyclePhase.RUNTIME))
    kernel.set_phase(LifecyclePhase.MAINTENANCE)
    other_phase = kernel.admit(_restart_request("shared-corr", phase=LifecyclePhase.MAINTENANCE))

    assert first.outcome == AdmissionOutcome.ALLOW
    assert other_correlation.outcome == AdmissionOutcome.ALLOW
    assert other_phase.outcome == AdmissionOutcome.ALLOW
    assert kernel.admission_dedupe_status().expires_at_by_key.keys() == {
        (LifecyclePhase.RUNTIME.value, "shared-corr"),
        (LifecyclePhase.RUNTIME.value, "other-corr"),
        (LifecyclePhase.MAINTENANCE.value, "shared-corr"),
    }


def test_dedupe_entries_expire_and_allow_correlation_reuse(tmp_path):
    clock = MutableClock(300.0)
    kernel = ControlPlaneKernel(
        runtime_governor=FakeRuntimeGovernor(),
        decisions_path=tmp_path / "decisions.jsonl",
        admission_dedupe_ttl_seconds=10.0,
        clock=clock,
    )

    first = kernel.admit(_restart_request("ttl-corr"))
    duplicate = kernel.admit(_restart_request("ttl-corr"))
    clock.advance(10.0)
    after_expiry = kernel.admit(_restart_request("ttl-corr"))

    assert first.outcome == AdmissionOutcome.ALLOW
    assert duplicate.outcome == AdmissionOutcome.DEFER
    assert "duplicate_admission_context" in duplicate.reason_codes
    assert after_expiry.outcome == AdmissionOutcome.ALLOW
    status = kernel.admission_dedupe_status()
    assert status.current_entries == 1
    assert status.expires_at_by_key == {(LifecyclePhase.RUNTIME.value, "ttl-corr"): 320.0}


def test_dedupe_cache_is_bounded_without_evicting_live_keys(tmp_path):
    clock = MutableClock(400.0)
    kernel = ControlPlaneKernel(
        runtime_governor=FakeRuntimeGovernor(),
        decisions_path=tmp_path / "decisions.jsonl",
        admission_dedupe_ttl_seconds=100.0,
        admission_dedupe_max_entries=2,
        clock=clock,
    )

    first = kernel.admit(_restart_request("bounded-1"))
    second = kernel.admit(_restart_request("bounded-2"))
    over_capacity = kernel.admit(_restart_request("bounded-3"))
    duplicate_first = kernel.admit(_restart_request("bounded-1"))

    assert first.outcome == AdmissionOutcome.ALLOW
    assert second.outcome == AdmissionOutcome.ALLOW
    assert over_capacity.outcome == AdmissionOutcome.DEFER
    assert "admission_dedupe_cache_full" in over_capacity.reason_codes
    assert over_capacity.delegated_outcomes["admission_dedupe"]["current_entries"] == 2
    assert duplicate_first.outcome == AdmissionOutcome.DEFER
    assert "duplicate_admission_context" in duplicate_first.reason_codes
    assert kernel.admission_dedupe_status().current_entries == 2


def test_dedupe_cache_compacts_expired_entries_before_capacity_check(tmp_path):
    clock = MutableClock(500.0)
    kernel = ControlPlaneKernel(
        runtime_governor=FakeRuntimeGovernor(),
        decisions_path=tmp_path / "decisions.jsonl",
        admission_dedupe_ttl_seconds=5.0,
        admission_dedupe_max_entries=1,
        clock=clock,
    )

    assert kernel.admit(_restart_request("old-corr")).outcome == AdmissionOutcome.ALLOW
    clock.advance(5.0)
    assert kernel.admit(_restart_request("new-corr")).outcome == AdmissionOutcome.ALLOW

    status = kernel.admission_dedupe_status()
    assert status.current_entries == 1
    assert status.expires_at_by_key == {(LifecyclePhase.RUNTIME.value, "new-corr"): 510.0}


def test_governor_denial_is_not_converted_to_duplicate_deferral(tmp_path):
    governor = FakeRuntimeGovernor(allow=False, reason="operator_lockout")
    kernel = ControlPlaneKernel(runtime_governor=governor, decisions_path=tmp_path / "decisions.jsonl")

    first = kernel.admit(_restart_request("deny-corr"))
    second = kernel.admit(_restart_request("deny-corr"))

    assert first.outcome == AdmissionOutcome.DENY
    assert second.outcome == AdmissionOutcome.DENY
    assert "runtime_governor:operator_lockout" in first.reason_codes
    assert "runtime_governor:operator_lockout" in second.reason_codes
    assert "duplicate_admission_context" not in second.reason_codes
    assert kernel.admission_dedupe_status().current_entries == 0


def test_proof_budget_delegate_unavailable_is_deferred(monkeypatch: pytest.MonkeyPatch, tmp_path):
    def _import_fail(name, *args, **kwargs):
        if name == "codex.proof_budget_governor":
            raise ImportError("no governor")
        return _orig_import(name, *args, **kwargs)

    import builtins

    _orig_import = builtins.__import__
    monkeypatch.setattr(builtins, "__import__", _import_fail)

    kernel = ControlPlaneKernel(runtime_governor=FakeRuntimeGovernor(), decisions_path=tmp_path / "decisions.jsonl")
    kernel.set_phase(LifecyclePhase.MAINTENANCE)
    decision = kernel.admit(
        ControlActionRequest(
            action_kind="proposal_eval",
            authority_class=AuthorityClass.PROPOSAL_EVALUATION,
            actor="forge",
            target_subsystem="capability-z",
            requested_phase=LifecyclePhase.MAINTENANCE,
            proof_budget_context={"config": object(), "pressure_state": object(), "run_context": {}},
        )
    )
    assert decision.outcome == AdmissionOutcome.DEFER
    assert "proof_budget_delegate_unavailable" in decision.reason_codes


def test_decision_log_write_failure_does_not_abort(monkeypatch: pytest.MonkeyPatch, tmp_path):
    kernel = ControlPlaneKernel(runtime_governor=FakeRuntimeGovernor(), decisions_path=tmp_path / "decisions.jsonl")

    def _boom(payload):
        raise OSError("disk full")

    monkeypatch.setattr(kernel, "_append", _boom)
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
    assert decision.outcome == AdmissionOutcome.ALLOW


def test_decision_schema_contains_normalized_fields(tmp_path):
    kernel = ControlPlaneKernel(runtime_governor=FakeRuntimeGovernor(), decisions_path=tmp_path / "decisions.jsonl")
    kernel.admit(
        ControlActionRequest(
            action_kind="restart_daemon",
            authority_class=AuthorityClass.DAEMON_RESTART,
            actor="healer",
            target_subsystem="daemon-x",
            requested_phase=LifecyclePhase.RUNTIME,
            metadata={"subject": "daemon-x", "correlation_id": "schema-1"},
        )
    )
    payload = (tmp_path / "decisions.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1]
    assert '"final_disposition": "allow"' in payload
    assert '"actor_source": "healer"' in payload
    assert '"delegate_checks_consulted": [' in payload


def test_privileged_operator_control_consults_runtime_governor(tmp_path):
    kernel = ControlPlaneKernel(runtime_governor=FakeRuntimeGovernor(), decisions_path=tmp_path / "decisions.jsonl")
    kernel.set_phase(LifecyclePhase.MAINTENANCE)
    decision = kernel.admit(
        ControlActionRequest(
            action_kind="quarantine_clear",
            authority_class=AuthorityClass.PRIVILEGED_OPERATOR_CONTROL,
            actor="operator_cli",
            target_subsystem="integrity_quarantine",
            requested_phase=LifecyclePhase.MAINTENANCE,
            metadata={"correlation_id": "op-1"},
        )
    )
    assert decision.outcome == AdmissionOutcome.ALLOW
    assert "runtime_governor" in decision.delegated_outcomes


def test_non_maintenance_restart_remains_unresolved_for_authority_reconciliation(tmp_path):
    kernel = ControlPlaneKernel(runtime_governor=FakeRuntimeGovernor(), decisions_path=tmp_path / "decisions.jsonl")
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
    assert decision.outcome == AdmissionOutcome.ALLOW
    assert decision.delegated_outcomes.get("authority_of_judgment") is None
    assert "authority_reconciliation:maintenance_proof_budget_authoritative" not in decision.reason_codes
