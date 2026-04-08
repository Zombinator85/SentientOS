from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from sentientos.control_plane_kernel import (
    AdmissionOutcome,
    AuthorityClass,
    ControlActionDecision,
    LifecyclePhase,
)
from sentientos.federation_canonical_execution import (
    FederationCanonicalExecutionRouter,
    reset_federation_canonical_execution_router,
)


@dataclass
class _FakeKernel:
    decision: ControlActionDecision

    def admit(self, request):  # noqa: ANN001
        return self.decision


def _decision(*, allowed: bool, reason: str = "admitted") -> ControlActionDecision:
    return ControlActionDecision(
        outcome=AdmissionOutcome.ALLOW if allowed else AdmissionOutcome.DENY,
        reason_codes=(reason,),
        current_phase=LifecyclePhase.RUNTIME,
        requested_phase=LifecyclePhase.RUNTIME,
        authority_class=AuthorityClass.FEDERATED_CONTROL,
        action_kind="restart_daemon",
        actor="peer-a",
        target_subsystem="alpha",
        delegated_outcomes={"runtime_governor": {"allowed": allowed}},
        correlation_id="corr-1",
    )


def test_router_fails_closed_when_required_metadata_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "glow/federation"))
    monkeypatch.setattr(
        "sentientos.federation_canonical_execution.get_control_plane_kernel",
        lambda: _FakeKernel(_decision(allowed=True)),
    )
    router = FederationCanonicalExecutionRouter()

    with pytest.raises(ValueError, match="missing_required_metadata:subject"):
        router.execute(
            typed_action_id="sentientos.federation.restart_daemon_request",
            peer_name="peer-a",
            action_kind="restart_daemon",
            target_subsystem="alpha",
            correlation_id="corr-1",
            metadata={"correlation_id": "corr-1", "scope": "federated"},
            handler=lambda: {"ok": True},
        )


def test_router_denial_is_machine_readable(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "glow/federation"))
    monkeypatch.setattr(
        "sentientos.federation_canonical_execution.get_control_plane_kernel",
        lambda: _FakeKernel(_decision(allowed=False, reason="runtime_governor:blocked")),
    )
    router = FederationCanonicalExecutionRouter()

    result = router.execute(
        typed_action_id="sentientos.federation.restart_daemon_request",
        peer_name="peer-a",
        action_kind="restart_daemon",
        target_subsystem="alpha",
        correlation_id="corr-1",
        metadata={"correlation_id": "corr-1", "subject": "alpha", "scope": "federated"},
        handler=lambda: {"ok": True},
    )

    assert result.canonical_outcome == "denied_pre_execution"
    assert result.admitted is False
    rows = (tmp_path / "glow/federation/canonical_execution.jsonl").read_text(encoding="utf-8").splitlines()
    payload = json.loads(rows[-1])
    assert payload["canonical_outcome"] == "denied_pre_execution"
    assert payload["proof_linkage_present"] is True


def test_router_admitted_failure_is_explicit(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "glow/federation"))
    monkeypatch.setattr(
        "sentientos.federation_canonical_execution.get_control_plane_kernel",
        lambda: _FakeKernel(_decision(allowed=True)),
    )
    router = FederationCanonicalExecutionRouter()

    result = router.execute(
        typed_action_id="sentientos.federation.governance_digest_or_quorum_denial_gate",
        peer_name="peer-a",
        action_kind="federated_control",
        target_subsystem="peer-a:federation",
        correlation_id="corr-1",
        metadata={"correlation_id": "corr-1", "subject": "peer-a:federation", "scope": "federated"},
        handler=lambda: (_ for _ in ()).throw(RuntimeError("gate_failure")),
    )

    assert result.canonical_outcome == "admitted_failed"
    assert result.admitted is True
    assert result.failure and result.failure["exception_type"] == "RuntimeError"


def test_router_rejects_out_of_scope_action_id(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "glow/federation"))
    monkeypatch.setattr(
        "sentientos.federation_canonical_execution.get_control_plane_kernel",
        lambda: _FakeKernel(_decision(allowed=True)),
    )
    router = FederationCanonicalExecutionRouter()

    with pytest.raises(ValueError, match="out_of_scope_or_unregistered_typed_action"):
        router.execute(
            typed_action_id="sentientos.federation.untyped_sync",
            peer_name="peer-a",
            action_kind="federated_control",
            target_subsystem="peer-a:federation",
            correlation_id="corr-1",
            metadata={"correlation_id": "corr-1", "subject": "peer-a:federation", "scope": "federated"},
            handler=lambda: {"ok": True},
        )


@pytest.fixture(autouse=True)
def _reset_router_state() -> None:
    reset_federation_canonical_execution_router()
