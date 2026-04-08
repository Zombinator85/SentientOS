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
from sentientos.daemons import pulse_federation


@dataclass(frozen=True)
class _Trust:
    trusted: bool
    classification: str = "current_trusted_epoch"
    epoch_id: str = "epoch-0001"


@dataclass(frozen=True)
class _Evaluation:
    denial_cause: str
    calibration_action: str

    def to_dict(self) -> dict[str, object]:
        return {
            "denial_cause": self.denial_cause,
            "calibration_action": self.calibration_action,
            "digest_status": "compatible",
            "quorum_required": 1,
            "quorum_present": 1,
            "quorum_satisfied": True,
        }


class _Governance:
    def __init__(self, evaluation: _Evaluation) -> None:
        self._evaluation = evaluation

    def evaluate_peer_event(self, peer_name: str, event: dict[str, object]) -> _Evaluation:  # noqa: ARG002
        return self._evaluation


class _Ledger:
    def record_epoch_classification(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return None

    def record_control_attempt(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return None

    def record_replay_signal(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return None


class _Governor:
    def observe_pulse_event(self, event):  # noqa: ANN001
        return None


@dataclass
class _Kernel:
    decision: ControlActionDecision

    def admit(self, request):  # noqa: ANN001
        return self.decision


def _decision(*, allowed: bool, correlation_id: str = "corr-1") -> ControlActionDecision:
    return ControlActionDecision(
        outcome=AdmissionOutcome.ALLOW if allowed else AdmissionOutcome.DENY,
        reason_codes=("admitted",) if allowed else ("runtime_governor:blocked",),
        current_phase=LifecyclePhase.RUNTIME,
        requested_phase=LifecyclePhase.RUNTIME,
        authority_class=AuthorityClass.FEDERATED_CONTROL,
        action_kind="restart_daemon",
        actor="peer-a",
        target_subsystem="alpha",
        delegated_outcomes={"runtime_governor": {"allowed": allowed}},
        correlation_id=correlation_id,
    )


@pytest.fixture(autouse=True)
def _reset(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "glow/federation"))
    monkeypatch.setenv("SENTIENTOS_CONTROL_KERNEL_ROOT", str(tmp_path / "glow/control_plane"))
    pulse_federation.reset()
    pulse_federation.configure(enabled=True, peers=["peer-a"])
    monkeypatch.setattr(pulse_federation, "verify_remote_signature", lambda event, peer_name: True)
    monkeypatch.setattr(pulse_federation, "_classify_protocol_compatibility", lambda claim: ("exact_protocol_match", [], {}))
    monkeypatch.setattr(
        pulse_federation,
        "_classify_replay_horizon",
        lambda event, claim: ("peer_within_compatible_replay_horizon", {"age_seconds": 0}),
    )
    monkeypatch.setattr(pulse_federation, "_classify_equivocation", lambda **kwargs: ("no_equivocation_evidence", []))
    monkeypatch.setattr(pulse_federation, "get_trust_ledger", lambda: _Ledger())
    monkeypatch.setattr(pulse_federation, "get_runtime_governor", lambda: _Governor())
    monkeypatch.setattr(
        pulse_federation.pulse_bus,
        "ingest_verified",
        lambda event, source_peer=None: {**event, "source_peer": source_peer or "peer-a"},
    )


def test_restart_intent_e2e_routes_to_canonical(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(pulse_federation, "get_trust_epoch_manager", lambda: type("M", (), {"classify_epoch": lambda *a, **k: _Trust(True)})())
    monkeypatch.setattr(pulse_federation, "get_federated_governance_controller", lambda: _Governance(_Evaluation("none", "observe")))

    event = {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "event_type": "restart_request",
        "correlation_id": "corr-1",
        "payload": {"action": "restart_daemon", "daemon_name": "alpha", "scope": "federated"},
        "pulse_protocol": {"schema_family": "pulse", "protocol_version": "2.2.0", "protocol_fingerprint": "x", "replay_policy": {"policy_version": "federation_replay_v1", "window_seconds": 1200, "tolerance_seconds": 120}},
    }

    result = pulse_federation.ingest_remote_event(event, "peer-a")
    assert result["source_peer"] == "peer-a"

    rows = [json.loads(line) for line in (tmp_path / "glow/federation/canonical_execution.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[-1]["typed_action_id"] == "sentientos.federation.restart_daemon_request"
    assert rows[-1]["canonical_outcome"] == "admitted_succeeded"
    assert rows[-1]["proof_linkage_present"] is True


def test_governance_denial_emits_canonical_denied_semantics(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(pulse_federation, "get_trust_epoch_manager", lambda: type("M", (), {"classify_epoch": lambda *a, **k: _Trust(True)})())
    monkeypatch.setattr(
        pulse_federation,
        "get_federated_governance_controller",
        lambda: _Governance(_Evaluation("quorum_failure", "deny")),
    )
    monkeypatch.setattr(
        "sentientos.federation_canonical_execution.get_control_plane_kernel",
        lambda: _Kernel(_decision(allowed=False)),
    )

    event = {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "event_type": "restart_request",
        "correlation_id": "corr-2",
        "payload": {"action": "restart_daemon", "daemon_name": "alpha", "scope": "federated"},
        "pulse_protocol": {"schema_family": "pulse", "protocol_version": "2.2.0", "protocol_fingerprint": "x", "replay_policy": {"policy_version": "federation_replay_v1", "window_seconds": 1200, "tolerance_seconds": 120}},
    }

    with pytest.raises(ValueError, match="Federated action denied"):
        pulse_federation.ingest_remote_event(event, "peer-a")

    rows = [json.loads(line) for line in (tmp_path / "glow/federation/canonical_execution.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[-1]["typed_action_id"] == "sentientos.federation.governance_digest_or_quorum_denial_gate"
    assert rows[-1]["canonical_outcome"] == "denied_pre_execution"
