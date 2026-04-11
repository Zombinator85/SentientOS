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
from sentientos.federation_bounded_lifecycle import (
    build_bounded_federation_latest_lifecycle_rows,
    build_bounded_federation_trace_coherence_map,
    resolve_bounded_federation_lifecycle,
)
from sentientos.federation_slice_health import synthesize_bounded_federation_seed_health


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


@pytest.fixture(autouse=True)
def _reset(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
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


def _decision(*, allowed: bool, correlation_id: str) -> ControlActionDecision:
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


def _event(correlation_id: str) -> dict[str, object]:
    return {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "event_type": "restart_request",
        "correlation_id": correlation_id,
        "payload": {"action": "restart_daemon", "daemon_name": "alpha", "scope": "federated"},
        "pulse_protocol": {
            "schema_family": "pulse",
            "protocol_version": "2.2.0",
            "protocol_fingerprint": "x",
            "replay_policy": {
                "policy_version": "federation_replay_v1",
                "window_seconds": 1200,
                "tolerance_seconds": 120,
            },
        },
    }


def test_success_lifecycle_resolves_end_to_end(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(pulse_federation, "get_trust_epoch_manager", lambda: type("M", (), {"classify_epoch": lambda *a, **k: _Trust(True)})())
    monkeypatch.setattr(pulse_federation, "get_federated_governance_controller", lambda: _Governance(_Evaluation("none", "observe")))

    pulse_federation.ingest_remote_event(_event("corr-success"), "peer-a")

    lifecycle = resolve_bounded_federation_lifecycle(
        tmp_path,
        typed_action_id="sentientos.federation.restart_daemon_request",
        correlation_id="corr-success",
    )
    assert lifecycle["outcome_class"] == "success"
    assert lifecycle["canonical_lifecycle_state"] == "resolved"
    assert lifecycle["proof_linkage"] == "present"


def test_denied_lifecycle_resolves_for_governance_gate(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(pulse_federation, "get_trust_epoch_manager", lambda: type("M", (), {"classify_epoch": lambda *a, **k: _Trust(True)})())
    monkeypatch.setattr(
        pulse_federation,
        "get_federated_governance_controller",
        lambda: _Governance(_Evaluation("quorum_failure", "observe")),
    )
    monkeypatch.setattr(
        "sentientos.federation_canonical_execution.get_control_plane_kernel",
        lambda: _Kernel(_decision(allowed=False, correlation_id="corr-denied")),
    )

    with pytest.raises(ValueError, match="Federated action denied"):
        pulse_federation.ingest_remote_event(_event("corr-denied"), "peer-a")

    lifecycle = resolve_bounded_federation_lifecycle(
        tmp_path,
        typed_action_id="sentientos.federation.governance_digest_or_quorum_denial_gate",
        correlation_id="corr-denied",
    )
    assert lifecycle["outcome_class"] == "denied"
    assert lifecycle["proof_linkage"] == "present"


def test_admitted_failure_lifecycle_resolves(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(pulse_federation, "get_trust_epoch_manager", lambda: type("M", (), {"classify_epoch": lambda *a, **k: _Trust(True)})())
    monkeypatch.setattr(
        pulse_federation,
        "get_federated_governance_controller",
        lambda: _Governance(_Evaluation("quorum_failure", "deny")),
    )
    monkeypatch.setattr(
        "sentientos.federation_canonical_execution.get_control_plane_kernel",
        lambda: _Kernel(_decision(allowed=True, correlation_id="corr-fail")),
    )

    with pytest.raises(ValueError, match="Federated action denied"):
        pulse_federation.ingest_remote_event(_event("corr-fail"), "peer-a")

    lifecycle = resolve_bounded_federation_lifecycle(
        tmp_path,
        typed_action_id="sentientos.federation.governance_digest_or_quorum_denial_gate",
        correlation_id="corr-fail",
    )
    assert lifecycle["outcome_class"] == "failed_after_admission"
    assert lifecycle["canonical_lifecycle_state"] == "resolved"


def test_fragmented_and_out_of_scope_paths_are_marked_honestly(tmp_path: Path) -> None:
    root = tmp_path / "glow/federation"
    root.mkdir(parents=True, exist_ok=True)
    (root / "canonical_execution.jsonl").write_text(
        json.dumps(
            {
                "typed_action_id": "sentientos.federation.restart_daemon_request",
                "correlation_id": "corr-fragmented",
                "canonical_outcome": "admitted_succeeded",
                "side_effect_status": "side_effect_committed",
                "admission_decision_ref": "kernel_decision:corr-fragmented",
                "proof_linkage_present": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    fragmented = resolve_bounded_federation_lifecycle(
        tmp_path,
        typed_action_id="sentientos.federation.restart_daemon_request",
        correlation_id="corr-fragmented",
    )
    assert fragmented["outcome_class"] == "fragmented_unresolved"
    assert fragmented["proof_linkage"] == "missing"

    out_of_scope = resolve_bounded_federation_lifecycle(
        tmp_path,
        typed_action_id="sentientos.federation.untyped_sync",
        correlation_id="corr-any",
    )
    assert out_of_scope["outcome_class"] == "fragmented_unresolved"
    assert out_of_scope["findings"][0]["kind"] == "out_of_scope_typed_action"


def test_trace_coherence_map_exposes_counts(tmp_path: Path) -> None:
    root = tmp_path / "glow/federation"
    root.mkdir(parents=True, exist_ok=True)
    row = {
        "typed_action_id": "sentientos.federation.restart_daemon_request",
        "correlation_id": "corr-map",
        "canonical_outcome": "admitted_succeeded",
        "side_effect_status": "side_effect_committed",
        "admission_decision_ref": "kernel_decision:corr-map",
        "proof_linkage_present": True,
    }
    (root / "canonical_execution.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    (root / "ingest_classifications.jsonl").write_text(
        json.dumps(
            {
                "typed_action_id": "sentientos.federation.restart_daemon_request",
                "correlation_id": "corr-map",
                "admission_decision_ref": "kernel_decision:corr-map",
                "canonical_outcome": "admitted_succeeded",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    coherence = build_bounded_federation_trace_coherence_map(tmp_path)
    assert coherence["outcome_class_counts"]["success"] == 1


def test_latest_lifecycle_rows_use_latest_observed_correlation(tmp_path: Path) -> None:
    root = tmp_path / "glow/federation"
    root.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "typed_action_id": "sentientos.federation.restart_daemon_request",
            "correlation_id": "corr-old",
            "canonical_outcome": "admitted_succeeded",
            "side_effect_status": "side_effect_committed",
            "admission_decision_ref": "kernel_decision:corr-old",
            "proof_linkage_present": True,
        },
        {
            "typed_action_id": "sentientos.federation.restart_daemon_request",
            "correlation_id": "corr-new",
            "canonical_outcome": "denied_pre_execution",
            "side_effect_status": "no_side_effect",
            "admission_decision_ref": "kernel_decision:corr-new",
            "proof_linkage_present": True,
        },
    ]
    (root / "canonical_execution.jsonl").write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    (root / "ingest_classifications.jsonl").write_text(
        json.dumps(
            {
                "typed_action_id": "sentientos.federation.restart_daemon_request",
                "correlation_id": "corr-new",
                "admission_decision_ref": "kernel_decision:corr-new",
                "canonical_outcome": "denied_pre_execution",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    latest_rows = build_bounded_federation_latest_lifecycle_rows(tmp_path)
    restart_row = next(row for row in latest_rows if row["typed_action_identity"] == "sentientos.federation.restart_daemon_request")
    assert restart_row["correlation_id"] == "corr-new"
    assert restart_row["outcome_class"] == "denied"


def test_replay_gate_e2e_lifecycle_and_health_inclusion(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(pulse_federation, "get_trust_epoch_manager", lambda: type("M", (), {"classify_epoch": lambda *a, **k: _Trust(True)})())
    monkeypatch.setattr(pulse_federation, "get_federated_governance_controller", lambda: _Governance(_Evaluation("none", "observe")))
    monkeypatch.setattr(
        pulse_federation,
        "_classify_replay_horizon",
        lambda event, claim: ("incompatible_replay_policy", {"age_seconds": 7200}),
    )

    with pytest.raises(ValueError):
        pulse_federation.ingest_remote_event(_event("corr-replay-health"), "peer-a")

    lifecycle = resolve_bounded_federation_lifecycle(
        tmp_path,
        typed_action_id="sentientos.federation.ingest_replay_admission_gate",
        correlation_id="corr-replay-health",
    )
    assert lifecycle["outcome_class"] == "success"
    assert lifecycle["proof_linkage"] == "present"
    latest = build_bounded_federation_latest_lifecycle_rows(tmp_path)
    assert any(row["typed_action_identity"] == "sentientos.federation.ingest_replay_admission_gate" for row in latest)
    health = synthesize_bounded_federation_seed_health(latest)
    assert "sentientos.federation.ingest_replay_admission_gate" in health["per_intent_latest_outcome"]
