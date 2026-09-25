from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sentientos.resident_cognitive_model_transition_experiment import PHASES, TransitionError, digest
from sentientos.resident_cognitive_transition_operator import (
    CONFIG_SCHEMA, JOURNAL_CUSTODY, REQUEST_CUSTODY, LiveTransitionConfig,
    LiveTransitionOperatorRuntime, build_request, persist_request,
)

pytestmark = pytest.mark.no_legacy_skip
NOW = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)


class _Session:
    session_id = "session-a"
    binding = {"observed_loaded_model_identity": {"model_id": "A"}}


class _Slot:
    current_controller = type("Controller", (), {"current_session": lambda self: _Session()})()


class _Gate:
    quiesced = False


class _Controller:
    def __init__(self) -> None:
        self.phase = PHASES[0]
        self.calls = 0
        self.protocol = type("Protocol", (), {"value": {"transition_id": "transition-1"}})()

    def health(self):
        return {"phase": self.phase, "journal_head": "GENESIS" if not self.calls else f"head-{self.calls}",
                "status": "in_progress"}

    def advance(self, *, approval, evidence=None):
        self.calls += 1
        prior = self.phase
        self.phase = PHASES[PHASES.index(self.phase) + 1]
        return {"prior_phase": prior, "phase": self.phase, "journal_head": f"head-{self.calls}",
                "advanced_one_stage": True}


def _approval(stage: str = PHASES[1]) -> dict[str, object]:
    body: dict[str, object] = {"schema_version": "sentientos.resident_cognitive_transition_stage_operator_approval:v1",
                              "requested_stage": stage}
    return {**body, "approval_digest": digest(body)}


def _config() -> LiveTransitionConfig:
    return LiveTransitionConfig(True, "installation-1", "protocol-1", "a" * 64,
                                REQUEST_CUSTODY, JOURNAL_CUSTODY, "journal-1")


def _request(**changes):
    values = dict(installation_identity="installation-1",
        protocol={"protocol_id": "protocol-1", "protocol_digest": "a" * 64, "transition_id": "transition-1"},
        requested_stage=PHASES[1], expected_prior_phase=PHASES[0], expected_journal_head="GENESIS",
        stage_approval=_approval(), subordinate_approvals=[], operation_id="operation-1",
        correlation_id="correlation-1", operator_identity="operator-1",
        operator_provenance={"source": "local-console"}, created_at="2026-09-25T11:00:00+00:00",
        expires_at="2026-09-25T13:00:00+00:00")
    values.update(changes)
    return build_request(**values)


def _runtime(tmp_path: Path, controller=None, verifier=None):
    return LiveTransitionOperatorRuntime(config=_config(), installation_root=tmp_path,
        controller=controller or _Controller(), slot=_Slot(), gate=_Gate(),
        subordinate_verifier=verifier, clock=lambda: NOW)


def test_one_request_advances_exactly_one_stage_and_duplicate_is_no_effect(tmp_path: Path) -> None:
    controller = _Controller(); runtime = _runtime(tmp_path, controller)
    path = persist_request(tmp_path, _request())
    assert path.parent == tmp_path / REQUEST_CUSTODY
    assert runtime.process_one()["status"] == "stage_advanced"
    assert controller.calls == 1 and controller.phase == PHASES[1]
    assert runtime.process_one() == {"status": "already_consumed", "request_id": _request()["request_id"],
                                     "effect_performed": False}
    assert controller.calls == 1 and path.exists()


def test_processing_call_never_advances_second_pending_request(tmp_path: Path) -> None:
    controller = _Controller(); runtime = _runtime(tmp_path, controller)
    persist_request(tmp_path, _request())
    persist_request(tmp_path, _request(correlation_id="correlation-2", operation_id="operation-2"))
    assert runtime.process_one()["status"] == "stage_advanced"
    assert controller.calls == 1


@pytest.mark.parametrize(("mutation", "reason"), [
    ({"protocol": {"protocol_id": "wrong", "protocol_digest": "a" * 64, "transition_id": "transition-1"}}, "operator_request_protocol_mismatch"),
    ({"expected_prior_phase": "wrong"}, "operator_request_prior_phase_mismatch"),
    ({"expected_journal_head": "wrong"}, "operator_request_journal_head_mismatch"),
    ({"requested_stage": PHASES[2], "stage_approval": _approval(PHASES[2])}, "operator_request_stage_skipped"),
    ({"created_at": "2026-09-24T11:00:00+00:00", "expires_at": "2026-09-24T13:00:00+00:00"}, "operator_request_expired"),
])
def test_bound_request_faults_are_consumed_without_effect(tmp_path: Path, mutation, reason) -> None:
    controller = _Controller(); runtime = _runtime(tmp_path, controller)
    persist_request(tmp_path, _request(**mutation))
    result = runtime.process_one()
    assert result["status"] == "rejected" and result["reason"] == reason
    assert controller.calls == 0


def test_malformed_and_wrong_stage_approval_are_rejected(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.request_root.mkdir(parents=True)
    (runtime.request_root / "bad.json").write_text("[]", encoding="utf-8")
    assert runtime.process_one()["status"] == "rejected"
    with pytest.raises(TransitionError, match="operator_request_stage_approval_invalid"):
        _request(stage_approval={"approval_digest": "bad"})


@pytest.mark.parametrize("reason", ["activation_denied", "serving_failed"])
def test_subordinate_denial_prevents_transition_effect(tmp_path: Path, reason: str) -> None:
    def deny(stage, approvals):
        raise TransitionError(reason)
    controller = _Controller(); runtime = _runtime(tmp_path, controller, deny)
    persist_request(tmp_path, _request())
    assert runtime.process_one()["reason"] == reason
    assert controller.calls == 0


def test_interrupted_transition_request_is_rejected_and_status_is_read_only(tmp_path: Path) -> None:
    controller = _Controller()
    controller.advance = lambda **kwargs: (_ for _ in ()).throw(TransitionError("failed_or_unresolved_stage_replay_forbidden"))
    runtime = _runtime(tmp_path, controller); persist_request(tmp_path, _request())
    assert runtime.process_one()["reason"] == "failed_or_unresolved_stage_replay_forbidden"
    status = runtime.status()
    assert status["read_only"] is True and status["protocol_id"] == "protocol-1"


def test_config_requires_fixed_installation_relative_custody(tmp_path: Path) -> None:
    config = {"schema_version": CONFIG_SCHEMA, "enabled": True, "installation_identity": "installation-1",
              "protocol_id": "protocol-1", "protocol_digest": "a" * 64,
              "request_custody": REQUEST_CUSTODY, "journal_custody": JOURNAL_CUSTODY,
              "journal_identity": "journal-1"}
    path = tmp_path / "config.json"; path.write_text(json.dumps(config), encoding="utf-8")
    assert LiveTransitionConfig.load(path) == _config()
    config["request_custody"] = "/tmp/arbitrary"; path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(TransitionError, match="live_transition_config_invalid"):
        LiveTransitionConfig.load(path)
