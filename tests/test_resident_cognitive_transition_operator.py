from __future__ import annotations

import json
import multiprocessing
import time
import base64
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sentientos.resident_cognitive_model_transition_experiment import PHASES, TransitionError, digest
from sentientos.causal_resource_principal_ed25519 import CryptographyEd25519SignatureVerifier
from sentientos.resident_cognitive_transition_operator_authentication import (
    OPERATOR_PROVENANCE_SCHEMA, TrustedTransitionOperatorKey,
    TransitionOperatorProvenanceError, TransitionOperatorProvenanceVerifier, canonical_operator_request_payload,
    operator_request_claims_digest, provenance_digest_for, seal_request_with_operator_provenance,
)
from sentientos.resident_cognitive_transition_operator import (
    CONFIG_SCHEMA, CONFIG_SCHEMA_V2, JOURNAL_CUSTODY, REQUEST_CUSTODY, LiveTransitionConfig,
    LiveTransitionOperatorRuntime, build_request, persist_request,
)

pytestmark = pytest.mark.no_legacy_skip
NOW = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
_TEST_OPERATOR_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
_TEST_OPERATOR_PUBLIC_BYTES = _TEST_OPERATOR_PRIVATE_KEY.public_key().public_bytes(
    encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
_TEST_OPERATOR_PUBLIC_KEY = base64.urlsafe_b64encode(_TEST_OPERATOR_PUBLIC_BYTES).decode().rstrip("=")
_TEST_OPERATOR_KEY_ID = "ed25519-sha256:" + hashlib.sha256(_TEST_OPERATOR_PUBLIC_BYTES).hexdigest()


class _TestOperatorTrustStore:
    def lookup(self, *, operator_identity: str, signing_key_id: str, algorithm: str):
        if (operator_identity, signing_key_id, algorithm) != ("operator-1", _TEST_OPERATOR_KEY_ID, "ed25519"):
            return None
        return TrustedTransitionOperatorKey(operator_identity, signing_key_id, algorithm,
            _TEST_OPERATOR_PUBLIC_KEY, "2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z", "active")


def _operator_verifier():
    return TransitionOperatorProvenanceVerifier(trust_store=_TestOperatorTrustStore(),
        signature_verifier=CryptographyEd25519SignatureVerifier())


_DEFAULT_OPERATOR_VERIFIER = object()


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
    body: dict[str, object] = {"schema_version": "sentientos.resident_cognitive_transition_stage_operator_approval:v2",
                              "requested_stage": stage,
                              "approval_issuer_identity": "operator-1"}
    return {**body, "approval_digest": digest(body)}


def _config() -> LiveTransitionConfig:
    return LiveTransitionConfig(True, "installation-1", "protocol-1", "a" * 64,
                                REQUEST_CUSTODY, JOURNAL_CUSTODY, "journal-1",
                                operator_trust_catalog_version=1,
                                operator_trust_catalog_digest="sha256:" + "d" * 64)


def _request(**changes):
    values = dict(installation_identity="installation-1",
        protocol={"protocol_id": "protocol-1", "protocol_digest": "a" * 64, "transition_id": "transition-1"},
        requested_stage=PHASES[1], expected_prior_phase=PHASES[0], expected_journal_head="GENESIS",
        stage_approval=_approval(), subordinate_approvals=[], operation_id="operation-1",
        correlation_id="correlation-1", operator_identity="operator-1",
        operator_provenance={}, created_at="2026-09-25T11:00:00+00:00",
        expires_at="2026-09-25T13:00:00+00:00")
    values.update(changes)
    request = build_request(**values)
    signed_at = "2026-09-25T11:30:00Z"
    claims_digest = operator_request_claims_digest(request)
    signature = _TEST_OPERATOR_PRIVATE_KEY.sign(canonical_operator_request_payload(
        operator_identity=str(request["operator_identity"]), signing_key_id=_TEST_OPERATOR_KEY_ID,
        signed_at=signed_at, request_claims_digest=claims_digest))
    provenance = {"schema": OPERATOR_PROVENANCE_SCHEMA,
        "operator_identity": request["operator_identity"], "signing_key_id": _TEST_OPERATOR_KEY_ID,
        "algorithm": "ed25519", "signed_at": signed_at,
        "request_claims_digest": claims_digest,
        "signature": base64.urlsafe_b64encode(signature).decode().rstrip("=")}
    provenance["provenance_digest"] = provenance_digest_for(provenance)
    return seal_request_with_operator_provenance(request, provenance)


def _runtime(tmp_path: Path, controller=None, verifier=None,
             operator_provenance_verifier=_DEFAULT_OPERATOR_VERIFIER):
    provenance_verifier = (_operator_verifier() if operator_provenance_verifier is _DEFAULT_OPERATOR_VERIFIER
                           else operator_provenance_verifier)
    return LiveTransitionOperatorRuntime(config=_config(), installation_root=tmp_path,
        controller=controller or _Controller(), slot=_Slot(), gate=_Gate(),
        subordinate_verifier=verifier,
        operator_provenance_verifier=provenance_verifier,
        clock=lambda: NOW)


def test_operator_provenance_authenticates_exact_request_claims() -> None:
    request = _request()
    authenticated = _operator_verifier().verify(request, current_time=NOW)
    assert authenticated.operator_identity == "operator-1"
    assert authenticated.signing_key_id == _TEST_OPERATOR_KEY_ID
    assert authenticated.request_claims_digest == request["operator_provenance"]["request_claims_digest"]


def test_operator_provenance_rejects_claim_changes_and_revoked_key() -> None:
    request = _request()
    changed = {**request, "correlation_id": "substituted"}
    with pytest.raises(TransitionOperatorProvenanceError, match="operator_provenance_request_mismatch"):
        _operator_verifier().verify(changed, current_time=NOW)

    class RevokedTrustStore(_TestOperatorTrustStore):
        def lookup(self, **kwargs):
            entry = super().lookup(**kwargs)
            assert entry is not None
            return TrustedTransitionOperatorKey(entry.operator_identity, entry.signing_key_id,
                entry.algorithm, entry.public_key, entry.valid_from, entry.valid_until, "revoked")

    revoked = TransitionOperatorProvenanceVerifier(trust_store=RevokedTrustStore(),
        signature_verifier=CryptographyEd25519SignatureVerifier())
    with pytest.raises(TransitionOperatorProvenanceError, match="operator_provenance_key_not_active"):
        revoked.verify(request, current_time=NOW)


def test_missing_operator_trust_fails_closed_before_recovery_or_stage_effect(tmp_path: Path) -> None:
    controller = _Controller()
    recovery_calls = 0

    def journal_entries():
        nonlocal recovery_calls
        recovery_calls += 1
        return []

    controller.journal.entries = journal_entries
    runtime = _runtime(tmp_path, controller, operator_provenance_verifier=None)
    request = _request()
    persist_request(tmp_path, request)
    result = runtime.process_one()
    assert result["status"] == "rejected"
    assert result["reason"] == "operator_provenance_verifier_unavailable"
    assert result["effect_performed"] is False
    assert controller.calls == 0
    assert recovery_calls == 0


def test_missing_operator_trust_cannot_claim_recovered_journal_success(tmp_path: Path) -> None:
    controller = _Controller()
    request = _request()
    controller.journal.entries = lambda: [
        {"status": "attempted", "phase": PHASES[0], "entry_digest": "attempt",
         "evidence": {"attempted_stage": request["requested_stage"],
                      "approval_digest": request["stage_approval_digest"]}},
        {"status": "completed", "phase": request["requested_stage"], "entry_digest": "terminal",
         "evidence": {}},
    ]
    runtime = _runtime(tmp_path, controller, operator_provenance_verifier=None)
    persist_request(tmp_path, request)
    result = runtime.process_one()
    assert result["status"] == "rejected"
    assert result["reason"] == "operator_provenance_verifier_unavailable"
    assert result["effect_performed"] is False
    assert controller.calls == 0


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


def test_stage_admission_plan_delegates_explicit_approval_without_processing(tmp_path: Path) -> None:
    controller = _Controller()
    supplied = _approval()
    observed = []

    def plan_stage_admission(approval):
        observed.append(approval)
        return {
            "status": "stage_approval_candidate_state_bound",
            "approval_digest": approval["approval_digest"],
            "operator_origin_authenticated": False,
            "effect_performed": False, "execution_allowed": False,
            "grants_authority": False, "read_only": True,
        }

    controller.plan_stage_admission = plan_stage_admission
    runtime = _runtime(tmp_path, controller)

    plan = runtime.plan_stage_admission(supplied)

    assert plan["status"] == "stage_approval_candidate_state_bound"
    assert observed == [supplied]
    assert observed[0] is supplied
    assert plan["approval_digest"] == supplied["approval_digest"]
    assert plan["operator_origin_authenticated"] is False
    assert plan["effect_performed"] is False and plan["execution_allowed"] is False
    assert plan["grants_authority"] is False and plan["read_only"] is True
    assert controller.calls == 0
    assert not runtime.receipt_path.exists()
    assert not runtime.request_root.exists()


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
    assert projection["schema_version"] == "sentientos.resident_cognitive_transition_verified_stage_receipt:v3"
    authentication = projection["operator_authentication"]
    assert authentication["operator_identity"] == "operator-1"
    assert authentication["signing_key_id"] == _TEST_OPERATOR_KEY_ID
    assert authentication["request_claims_digest"] == packet["operator_provenance"]["request_claims_digest"]
    assert authentication["provenance_digest"] == packet["operator_provenance"]["provenance_digest"]
    assert authentication["trust_catalog_version"] == 1
    assert authentication["trust_catalog_digest"] == _config().operator_trust_catalog_digest
    with pytest.raises(TypeError):
        authentication["operator_identity"] = "substituted"
    assert projection["read_only"] is True
    assert projection["effect_performed"] is False
    assert projection["grants_authority"] is False
    assert projection["execution_allowed"] is False
    assert "stage_approval" not in projection
    assert runtime.receipt_path.read_bytes() == before
    assert controller.calls == calls_before

    class RevokedTrustStore(_TestOperatorTrustStore):
        def lookup(self, **kwargs):
            trusted = super().lookup(**kwargs)
            assert trusted is not None
            return TrustedTransitionOperatorKey(
                trusted.operator_identity, trusted.signing_key_id, trusted.algorithm,
                trusted.public_key, trusted.valid_from, trusted.valid_until, "revoked")

    runtime.operator_provenance_verifier = TransitionOperatorProvenanceVerifier(
        trust_store=RevokedTrustStore(),
        signature_verifier=CryptographyEd25519SignatureVerifier(),
    )
    with pytest.raises(
        TransitionError,
        match="operator_stage_receipt_operator_authentication_unavailable",
    ):
        runtime.inspect_verified_stage_receipt(packet["request_id"])
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


def test_authenticated_request_operator_must_match_stage_approval_issuer(tmp_path: Path) -> None:
    controller = _Controller(); runtime = _runtime(tmp_path, controller)
    approval = _approval()
    approval["approval_issuer_identity"] = "operator-2"
    approval = {**{key: value for key, value in approval.items() if key != "approval_digest"}}
    approval["approval_digest"] = digest(approval)
    persist_request(tmp_path, _request(stage_approval=approval))

    result = runtime.process_one()

    assert result["status"] == "rejected"
    assert result["reason"] == "operator_request_stage_approval_issuer_mismatch"
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
    legacy = LiveTransitionConfig.load(path)
    assert legacy == LiveTransitionConfig(True, "installation-1", "protocol-1", "a" * 64,
        REQUEST_CUSTODY, JOURNAL_CUSTODY, "journal-1")
    config = {**config, "schema_version": CONFIG_SCHEMA_V2,
              "operator_trust_catalog_version": 3,
              "operator_trust_catalog_digest": "sha256:" + "b" * 64}
    path.write_text(json.dumps(config), encoding="utf-8")
    loaded = LiveTransitionConfig.load(path)
    assert loaded.operator_trust_catalog_version == 3
    assert loaded.operator_trust_catalog_digest == "sha256:" + "b" * 64
    config["request_custody"] = "/tmp/arbitrary"; path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(TransitionError, match="live_transition_config_invalid"):
        LiveTransitionConfig.load(path)
