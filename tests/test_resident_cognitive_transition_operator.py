from __future__ import annotations

import json
import multiprocessing
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
    def to_dict(self):
        return {"session_id": self.session_id, "binding": self.binding}


class _Slot:
    current_controller = type("Controller", (), {
        "current_session": lambda self: _Session(),
        "observed_current_session": lambda self: _Session(),
    })()


class _Gate:
    quiesced = False


class _Controller:
    def __init__(self) -> None:
        self.phase = PHASES[0]
        self.calls = 0
        self.protocol = type("Protocol", (), {"value": {"transition_id": "transition-1"}})()
        self.journal = type("Journal", (), {"entries": lambda self: []})()

    def health(self):
        return {"phase": self.phase, "journal_head": "GENESIS" if not self.calls else f"head-{self.calls}",
                "status": "in_progress"}

    def advance(self, *, approval, evidence=None, stage_execution_context=None,
                operation_context=None):
        self.calls += 1
        prior = self.phase
        self.phase = PHASES[PHASES.index(self.phase) + 1]
        assert stage_execution_context is not None
        return {"prior_phase": prior, "phase": self.phase, "journal_head": f"head-{self.calls}",
                "advanced_one_stage": True}


class _CrossProcessController(_Controller):
    def __init__(self, calls: Any) -> None:
        super().__init__()
        self.shared_calls = calls

    def advance(self, **kwargs: Any) -> dict[str, Any]:
        with self.shared_calls.get_lock():
            self.shared_calls.value += 1
        # Give a competing process time to observe the same unconsumed packet.
        time.sleep(0.2)
        return super().advance(**kwargs)


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


def _process_one_transition_request(root: str, calls: Any, start: Any, results: Any) -> None:
    runtime = _runtime(Path(root), _CrossProcessController(calls))
    start.wait(timeout=5)
    results.put(runtime.process_one()["status"])


def test_one_request_advances_exactly_one_stage_and_duplicate_is_no_effect(tmp_path: Path) -> None:
    controller = _Controller(); runtime = _runtime(tmp_path, controller)
    path = persist_request(tmp_path, _request())
    assert path.parent == tmp_path / REQUEST_CUSTODY
    assert runtime.process_one()["status"] == "stage_advanced"
    assert controller.calls == 1 and controller.phase == PHASES[1]
    assert runtime.process_one() == {"status": "already_consumed", "request_id": _request()["request_id"],
                                     "effect_performed": False}
    assert controller.calls == 1 and path.exists()


def test_verified_stage_receipt_requires_completed_semantically_verified_journal_binding(
    tmp_path: Path,
) -> None:
    controller = _Controller()
    runtime = _runtime(tmp_path, controller)
    packet = _request(stage_evidence={"campaign_trial_id": "trial-1"})
    persist_request(tmp_path, packet)
    result = runtime.process_one()
    assert result["status"] == "stage_advanced"

    request_binding = {"request_id": packet["request_id"],
                       "request_digest": packet["request_digest"]}
    controller.journal.entries = lambda: [
        {"phase": PHASES[0], "status": "attempted",
         "evidence": {"attempted_stage": PHASES[1],
                      "approval_digest": packet["stage_approval_digest"],
                      "operator_request": request_binding},
         "entry_digest": "attempt-entry"},
        {"phase": PHASES[1], "status": "completed",
         "evidence": {"operator_request": request_binding},
         "entry_digest": "head-1"},
    ]
    controller.health = lambda: {
        "phase": PHASES[1], "journal_head": "head-1", "status": "in_progress",
        "semantically_verified_stage_entry_digests": ["head-1"],
    }
    before = runtime.receipt_path.read_bytes()
    calls_before = controller.calls
    verified_health = controller.health
    controller.health = lambda: {
        **verified_health(), "semantically_verified_stage_entry_digests": [],
    }
    with pytest.raises(
        TransitionError, match="operator_stage_receipt_semantic_verification_unavailable"
    ):
        runtime.inspect_verified_stage_receipt(packet["request_id"])
    controller.health = verified_health

    projection = runtime.inspect_verified_stage_receipt(packet["request_id"])

    assert projection["phase"] == PHASES[1]
    assert projection["operator_receipt_digest"] == result["receipt_digest"]
    assert projection["completed_entry_digest"] == "head-1"
    assert projection["campaign_trial_id"] == "trial-1"
    assert projection["schema_version"] == "sentientos.resident_cognitive_transition_verified_stage_receipt:v2"
    assert projection["read_only"] is True
    assert projection["effect_performed"] is False
    assert projection["grants_authority"] is False
    assert projection["execution_allowed"] is False
    assert "stage_approval" not in projection
    assert runtime.receipt_path.read_bytes() == before
    assert controller.calls == calls_before


def test_verified_stage_receipt_accepts_journal_recovered_completion(tmp_path: Path) -> None:
    controller = _Controller()
    runtime = _runtime(tmp_path, controller)
    packet = _request()
    request_binding = {"request_id": packet["request_id"],
                       "request_digest": packet["request_digest"]}
    terminal_digest = "recovered-terminal"
    controller.journal.entries = lambda: [
        {"phase": PHASES[0], "status": "attempted",
         "evidence": {"attempted_stage": PHASES[1],
                      "approval_digest": packet["stage_approval_digest"],
                      "operator_request": request_binding},
         "entry_digest": "recovered-attempt"},
        {"phase": PHASES[1], "status": "completed",
         "evidence": {"operator_request": request_binding},
         "entry_digest": terminal_digest},
    ]
    controller.advance = lambda **kwargs: (_ for _ in ()).throw(
        TransitionError("response_lost_after_commit"))
    persist_request(tmp_path, packet)
    result = runtime.process_one()
    assert result["status"] == "stage_advanced"
    assert result["recovered"] is True
    controller.health = lambda: {
        "phase": PHASES[1], "journal_head": terminal_digest, "status": "in_progress",
        "semantically_verified_stage_entry_digests": [terminal_digest],
    }

    projection = runtime.inspect_verified_stage_receipt(packet["request_id"])

    assert projection["completed_entry_digest"] == terminal_digest
    assert projection["operator_receipt_digest"] == result["receipt_digest"]
    assert projection["effect_performed"] is False
    assert projection["grants_authority"] is False


def test_verified_stage_receipt_rejects_rejected_or_missing_custody(tmp_path: Path) -> None:
    controller = _Controller()
    runtime = _runtime(tmp_path, controller)
    packet = _request()
    persist_request(tmp_path, packet)
    rejected = _request(correlation_id="rejected", operation_id="rejected")
    persist_request(tmp_path, rejected)
    controller.advance = lambda **kwargs: (_ for _ in ()).throw(
        TransitionError("stage_execution_interrupted"))
    runtime.process_one()
    with pytest.raises(TransitionError, match="operator_stage_receipt_unavailable"):
        runtime.inspect_verified_stage_receipt(rejected["request_id"])
    with pytest.raises(TransitionError, match="operator_stage_receipt_unavailable"):
        runtime.inspect_verified_stage_receipt(packet["request_id"])
    assert controller.calls == 0


def test_processing_call_never_advances_second_pending_request(tmp_path: Path) -> None:
    controller = _Controller(); runtime = _runtime(tmp_path, controller)
    persist_request(tmp_path, _request())
    persist_request(tmp_path, _request(correlation_id="correlation-2", operation_id="operation-2"))
    assert runtime.process_one()["status"] == "stage_advanced"
    assert controller.calls == 1


def test_duplicate_transition_requests_advance_once_across_processes(tmp_path: Path) -> None:
    context = multiprocessing.get_context("fork")
    calls = context.Value("i", 0)
    start = context.Barrier(2)
    results = context.Queue()
    persist_request(tmp_path, _request())
    workers = [context.Process(target=_process_one_transition_request,
        args=(str(tmp_path), calls, start, results)) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)
    live_workers = [worker for worker in workers if worker.is_alive()]
    for worker in live_workers:
        worker.terminate()
        worker.join(timeout=2)
    assert not live_workers
    assert all(worker.exitcode == 0 for worker in workers)
    assert sorted(results.get(timeout=2) for _ in workers) == ["already_consumed", "stage_advanced"]
    assert calls.value == 1


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
    # A packet with no verifiable request identity cannot receive an identity-bound
    # rejection receipt. Custody inspection must fail closed before processing.
    with pytest.raises(TransitionError, match="operator_request_custody_noncanonical_or_mismatched"):
        runtime.process_one()
    assert not runtime.receipt_path.exists()
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


def test_status_exposes_blocked_stage_and_reason_read_only(tmp_path: Path) -> None:
    controller = _Controller()
    controller.health = lambda: {
        "phase": PHASES[1], "journal_head": "journal-head",
        "status": "interrupted", "reason": "unresolved_attempt",
        "outstanding_stage": "a_quiesced", "replay_forbidden": True,
        "semantically_verified_stage_entry_digests": ["verified-entry-digest"],
    }
    runtime = _runtime(tmp_path, controller)
    status = runtime.status()
    assert status["interrupted"] is True
    assert status["recovery_reason"] == "unresolved_attempt"
    assert status["outstanding_stage"] == "a_quiesced"
    assert status["replay_forbidden"] is True
    assert status["semantically_verified_stage_entry_digests"] == ["verified-entry-digest"]
    assert status["read_only"] is True
    assert controller.calls == 0
    assert controller.journal.entries() == []


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
