"""Bounded, journal-authoritative A -> B -> A resident transition runner.

The runner coordinates owners; it never acquires activation, serving, inference, or
writeback authority.  In particular, an operator transition approval is only a
stage-order approval and cannot be presented to any subordinate authority owner.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterator, Mapping, Protocol, Sequence, cast
from .windows_handle_custody import WindowsHandleCustodyError, read_explicit_file
from .local_runtime_provisioning import semantic_digest

SCHEMA = "sentientos.resident_cognitive_model_transition_protocol:v1"
SCHEMA_V2 = "sentientos.resident_cognitive_model_transition_protocol:v2"
BINDING_SCHEMA = "sentientos.resident_cognitive_transition_stage_serving_binding:v2"
APPROVAL_SCHEMA = "sentientos.resident_cognitive_transition_stage_operator_approval:v1"
JOURNAL_SCHEMA = "sentientos.resident_cognitive_model_transition_journal_entry:v1"
CAPABILITY = "resident_cognitive_model_transition_experiment"
PRINCIPAL = "deterministic_resident_cognitive_model_transition_controller"
PHASES = ("predecessor_a_epoch_current", "a_to_b_transition_requested", "a_quiesced",
 "b_activation_committed", "b_serving_bound", "b_epoch_resumed", "b_epoch_observed",
 "b_to_a_restoration_requested", "b_quiesced", "a_restoration_activation_committed",
 "restored_a_serving_bound", "restored_a_epoch_resumed", "post_restoration_observed",
 "experiment_complete")
EFFECTFUL = frozenset({"b_activation_committed", "b_serving_bound",
                       "a_restoration_activation_committed", "restored_a_serving_bound"})
MAX_TRANSITION_JOURNAL_ENTRIES = 4096
MAX_TRANSITION_JOURNAL_BYTES = 16_777_216
MAX_TRANSITION_JOURNAL_ENTRY_BYTES = 262_144


class TransitionError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(cast(Any, value))
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    return value


def digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256((json.dumps(_plain(value), sort_keys=True,
                                      separators=(",", ":")) + "\n").encode()).hexdigest()


def history_boundary(records: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Compatibility helper for tests; runtime composition uses the durable store helper."""
    exact = [_plain(x) for x in records]
    body = {"schema_version": "sentientos.developmental_history_boundary:v2", "records": exact,
            "record_ids": [x.get("record_id") for x in exact],
            "record_digests": [x.get("record_digest") for x in exact],
            "writeback_receipt_ids": [], "writeback_receipt_digests": []}
    body["record_set_digest"] = digest({"record_ids": body["record_ids"],
                                         "record_digests": body["record_digests"]})
    return MappingProxyType({**body, "boundary_digest": digest(body)})


def developmental_history_boundary(*, store: Any, composition_state_path: Path,
                                   activation: Mapping[str, Any], session: Any) -> Mapping[str, Any]:
    """Verify and bind the complete durable developmental history boundary."""
    records = [asdict(record) for record in store.records()]
    receipts = [asdict(receipt) for receipt in store.receipts()]
    try:
        state_bytes = read_explicit_file(composition_state_path, max_bytes=16_777_216)
    except WindowsHandleCustodyError as exc:
        if str(exc) != "explicit_file_missing":
            raise TransitionError("composition_state_safe_read_failed") from exc
        state_bytes = None
    if state_bytes is not None:
        state = json.loads(state_bytes.decode("utf-8"))
        if (not isinstance(state, dict)
                or json.dumps(state, indent=2, sort_keys=True).encode("utf-8") + b"\n" != state_bytes):
            raise TransitionError("composition_state_noncanonical")
        claimed = state.get("state_digest")
        semantic = {k: v for k, v in state.items() if k != "state_digest"}
        from .local_model_authority import digest_payload
        if claimed != "sha256:" + digest_payload(semantic):
            raise TransitionError("composition_state_tamper")
    else:
        state = {"schema": "absent", "completed_ticks": [], "state_digest": digest({"state": "absent"})}
    boundary = dict(history_boundary(records))
    body = {**boundary,
            "writeback_receipt_ids": [x["receipt_id"] for x in receipts],
            "writeback_receipt_digests": [x["receipt_digest"] for x in receipts],
            "resident_composition_state_digest": state["state_digest"],
            "last_completed_tick": (state.get("completed_ticks") or [None])[-1],
            "current_activation": _plain(activation),
            "current_resident_serving_session": _plain(session.to_dict() if hasattr(session, "to_dict") else session)}
    body.pop("boundary_digest", None)
    return MappingProxyType({**body, "boundary_digest": digest(body)})


@dataclass(frozen=True)
class TransitionProtocol:
    value: Mapping[str, Any]

    @classmethod
    def create(cls, *, installation_identity: str, predecessor: Mapping[str, Any],
               successor: Mapping[str, Any], initial_activation: Mapping[str, Any],
               initial_session: Mapping[str, Any], initial_boundary: Mapping[str, Any],
               b_operation_id: str, restored_a_operation_id: str,
               model_replacement_protocol_references: Mapping[str, Mapping[str, str]] | None = None) -> "TransitionProtocol":
        if model_replacement_protocol_references is not None and not isinstance(model_replacement_protocol_references, Mapping):
            raise TransitionError("model_provenance_protocol_reference_invalid")
        references = _plain(model_replacement_protocol_references or {})
        if references:
            if not isinstance(references, dict) or set(references) - {"predecessor_a", "successor_b"}:
                raise TransitionError("model_provenance_protocol_reference_invalid")
            for reference in references.values():
                if (not isinstance(reference, dict)
                        or set(reference) != {"protocol_id", "protocol_digest", "model_role"}
                        or reference.get("model_role") not in {"model_a", "model_b"}
                        or not isinstance(reference.get("protocol_id"), str)
                        or not reference["protocol_id"].startswith("model-replacement-protocol-")
                        or not isinstance(reference.get("protocol_digest"), str)
                        or len(reference["protocol_digest"]) != 71
                        or not reference["protocol_digest"].startswith("sha256:")
                        or any(c not in "0123456789abcdef" for c in reference["protocol_digest"][7:])):
                    raise TransitionError("model_provenance_protocol_reference_invalid")
        body = {"schema_version": SCHEMA_V2 if references else SCHEMA,
                "installation_identity": installation_identity,
                "predecessor_a": _plain(predecessor), "successor_b": _plain(successor),
                "restored_a": _plain(predecessor), "initial_activation": _plain(initial_activation),
                "initial_resident_session": _plain(initial_session),
                "initial_history_boundary": _plain(initial_boundary), "phase_order": list(PHASES),
                "transitions": ["A->B", "B->A"], "b_serving_operation_id": b_operation_id,
                "restored_a_serving_operation_id": restored_a_operation_id,
                "failure_policy": "interrupt_no_retry_no_rollback", "grants_authority": False,
                "nonclaims": ["personal_identity", "consciousness_continuity", "selfhood_continuity",
                              "learning", "improvement"]}
        if references:
            body["model_replacement_protocol_references"] = references
        pd = digest(body)
        return cls(MappingProxyType({**body, "protocol_id": "resident-transition-protocol-" + pd[:24],
                                     "protocol_digest": pd, "transition_id": "transition-" + pd[:24]}))

    def verify(self) -> None:
        value = dict(self.value)
        claimed = value.pop("protocol_digest", None)
        protocol_id = value.pop("protocol_id", None)
        transition_id = value.pop("transition_id", None)
        schema = value.get("schema_version")
        references = value.get("model_replacement_protocol_references")
        if ((schema == SCHEMA and references is not None)
                or (schema == SCHEMA_V2 and (not isinstance(references, Mapping) or not references
                    or set(references) - {"predecessor_a", "successor_b"}))
                or schema not in {SCHEMA, SCHEMA_V2}
                or value.get("phase_order") != list(PHASES)
                or digest(value) != claimed or protocol_id != "resident-transition-protocol-" + str(claimed)[:24]
                or transition_id != "transition-" + str(claimed)[:24]):
            raise TransitionError("protocol_tamper")
        if schema == SCHEMA_V2:
            for reference in references.values():
                if (not isinstance(reference, Mapping)
                        or set(reference) != {"protocol_id", "protocol_digest", "model_role"}
                        or reference.get("model_role") not in {"model_a", "model_b"}
                        or not isinstance(reference.get("protocol_id"), str)
                        or not reference["protocol_id"].startswith("model-replacement-protocol-")
                        or not isinstance(reference.get("protocol_digest"), str)
                        or len(reference["protocol_digest"]) != 71
                        or not reference["protocol_digest"].startswith("sha256:")
                        or any(c not in "0123456789abcdef" for c in reference["protocol_digest"][7:])):
                    raise TransitionError("protocol_model_provenance_reference_invalid")


class ResidentCognitionQuiescenceGate:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._quiesced = False
        self._inflight = 0
        self._generation = 0
        self._token: Mapping[str, Any] | None = None

    @contextmanager
    def cycle(self) -> Iterator[None]:
        with self._condition:
            if self._quiesced:
                raise TransitionError("resident_cognition_quiesced")
            self._inflight += 1
        try:
            yield
        finally:
            with self._condition:
                self._inflight -= 1
                self._condition.notify_all()

    def quiesce(self, *, timeout_seconds: float, observation: Mapping[str, Any]) -> Mapping[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            self._quiesced = True
            while self._inflight:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._quiesced = False
                    self._condition.notify_all()
                    raise TransitionError("quiescence_timeout")
                self._condition.wait(remaining)
            self._generation += 1
            body = {"schema_version": "sentientos.resident_cognition_quiescence:v1",
                    "generation": self._generation, "no_inflight": True,
                    "observation": _plain(observation)}
            self._token = MappingProxyType({**body, "token": "quiescence-" + digest(body)[:24],
                                             "observation_digest": digest(body)})
            return self._token

    def verifies(self, token: Mapping[str, Any]) -> bool:
        with self._condition:
            return bool(self._quiesced and self._token is not None and dict(self._token) == dict(token)
                        and token.get("generation") == self._generation)

    def resume(self, token: Mapping[str, Any]) -> None:
        with self._condition:
            if not self.verifies(token):
                raise TransitionError("quiescence_token_mismatch")
            self._quiesced = False
            self._token = None
            self._condition.notify_all()

    @property
    def quiesced(self) -> bool:
        with self._condition:
            return self._quiesced


class QuiescedDevelopmentalCognitionOwner:
    def __init__(self, owner: Any, gate: ResidentCognitionQuiescenceGate):
        self._owner, self.gate = owner, gate

    def run_tick(self, **kwargs: Any) -> Any:
        with self.gate.cycle():
            return self._owner.run_tick(**kwargs)


class TransitionJournal:
    def __init__(self, path: Path):
        self.path = path

    def entries(self) -> list[dict[str, Any]]:
        try:
            raw = read_explicit_file(self.path, max_bytes=MAX_TRANSITION_JOURNAL_BYTES)
        except WindowsHandleCustodyError as exc:
            if str(exc) == "explicit_file_missing":
                return []
            raise TransitionError("journal_not_regular") from exc
        out: list[dict[str, Any]] = []
        prior = "GENESIS"
        lines = raw.splitlines()
        if len(lines) > MAX_TRANSITION_JOURNAL_ENTRIES or any(
                not line or len(line) > MAX_TRANSITION_JOURNAL_ENTRY_BYTES for line in lines):
            raise TransitionError("journal_retention_limit_exceeded")
        for number, line in enumerate(lines, 1):
            try:
                item = json.loads(line.decode("utf-8"))
                claimed = item.pop("entry_digest")
            except (TypeError, ValueError, KeyError, AttributeError, UnicodeError) as exc:
                raise TransitionError("journal_tamper") from exc
            legacy_keys = {"schema_version", "sequence", "prior_digest", "phase", "status", "evidence"}
            timestamped_keys = legacy_keys | {"event_time"}
            if (not isinstance(item, dict) or item.get("schema_version") != JOURNAL_SCHEMA or item.get("sequence") != number
                    or item.get("prior_digest") != prior or digest(item) != claimed
                    or frozenset(item) not in {frozenset(legacy_keys), frozenset(timestamped_keys)}
                    or item.get("phase") not in PHASES or not isinstance(item.get("evidence"), Mapping)
                    or ("event_time" in item and not isinstance(item["event_time"], str))
                    or item.get("status") not in {"attempted", "effected", "completed", "failed", "interrupted"}):
                raise TransitionError("journal_tamper")
            if json.dumps({**item, "entry_digest": claimed}, sort_keys=True,
                    separators=(",", ":")).encode("utf-8") + b"\n" != line:
                raise TransitionError("journal_noncanonical")
            if number > MAX_TRANSITION_JOURNAL_ENTRIES:
                raise TransitionError("journal_retention_limit_exceeded")
            item["entry_digest"] = claimed
            out.append(item)
            prior = claimed
        return out

    def append(self, phase: str, evidence: Mapping[str, Any], *, status: str = "completed") -> Mapping[str, Any]:
        if os.name != "posix":
            raise TransitionError("journal_publication_unsupported_platform")
        entries = self.entries()
        if (len(entries) >= MAX_TRANSITION_JOURNAL_ENTRIES or phase not in PHASES
                or status not in {"attempted", "effected", "completed", "failed", "interrupted"}):
            raise TransitionError("journal_retention_limit_or_phase_invalid")
        body = {"schema_version": JOURNAL_SCHEMA, "sequence": len(entries) + 1,
                "prior_digest": entries[-1]["entry_digest"] if entries else "GENESIS",
                "phase": phase, "status": status, "event_time": datetime.now(timezone.utc).isoformat(),
                "evidence": _plain(evidence)}
        item = {**body, "entry_digest": digest(body)}
        encoded = (json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        existing_size = self.path.stat().st_size if self.path.exists() else 0
        if (len(encoded) > MAX_TRANSITION_JOURNAL_ENTRY_BYTES
                or existing_size + len(encoded) > MAX_TRANSITION_JOURNAL_BYTES):
            raise TransitionError("journal_retention_limit_exceeded")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(descriptor, "ab") as stream:
            stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
        return MappingProxyType(item)


def stage_serving_binding(*, protocol: TransitionProtocol, stage: str,
                          activation: Mapping[str, Any], expected_identity: Mapping[str, Any],
                          operation_id: str) -> Mapping[str, Any]:
    protocol.verify()
    if stage not in {"b_serving_bound", "restored_a_serving_bound"}:
        raise TransitionError("serving_binding_stage_invalid")
    receipt_digest = activation.get("receipt_semantic_digest", activation.get("activation_receipt_semantic_digest"))
    body = {"schema_version": BINDING_SCHEMA, "protocol_id": protocol.value["protocol_id"],
            "protocol_digest": protocol.value["protocol_digest"],
            "transition_id": protocol.value["transition_id"], "stage": stage,
            "installation_identity": protocol.value["installation_identity"],
            "activation_state_digest": activation["state_semantic_digest"],
            "activation_generation": activation["generation"],
            "activation_receipt_id": activation["receipt_id"],
            "activation_receipt_digest": receipt_digest,
            "activation_history_digest": activation["activation_history_digest"],
            "expected_model_identity": _plain(expected_identity), "serving_operation_id": operation_id,
            "resident_serving_capability_id": "resident_cognitive_model_serving",
            "grants_activation": False, "grants_model_serving": False, "grants_inference": False}
    return MappingProxyType({**body, "binding_digest": digest(body)})


def verify_stage_serving_binding(binding: Mapping[str, Any], *, protocol: TransitionProtocol,
                                 stage: str, session: Any) -> None:
    value = dict(binding)
    claimed = value.pop("binding_digest", None)
    observed = _plain(session.binding.get("observed_loaded_model_identity"))
    if (value.get("schema_version") != BINDING_SCHEMA or digest(value) != claimed
            or value.get("protocol_id") != protocol.value["protocol_id"]
            or value.get("protocol_digest") != protocol.value["protocol_digest"]
            or value.get("transition_id") != protocol.value["transition_id"]
            or value.get("stage") != stage or value.get("serving_operation_id") != session.binding.get("serving_operation_id")
            or value.get("activation_state_digest") != session.binding.get("activation_state_semantic_digest")
            or value.get("activation_generation") != session.binding.get("activation_generation")
            or value.get("activation_receipt_id") != session.binding.get("activation_receipt_id")
            or value.get("activation_receipt_digest") != session.binding.get("activation_receipt_semantic_digest")
            or value.get("activation_history_digest") != session.binding.get("activation_history_digest")
            or value.get("expected_model_identity") != observed
            or any(value.get(key) is not False for key in ("grants_activation", "grants_model_serving", "grants_inference"))):
        raise TransitionError("transition_stage_serving_binding_mismatch")


class TransitionStageOperations(Protocol):
    def verify_historical_activation(self, activation: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def verify_historical_serving_session(self, session: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def verify_transition_observation(self, stage: str, evidence: Mapping[str, Any]) -> None: ...
    def activate_successor(self, context: "TransitionStageExecutionContext | None" = None) -> Mapping[str, Any]: ...
    def serve_successor(self, activation: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def activate_restored_predecessor(self, context: "TransitionStageExecutionContext | None" = None) -> Mapping[str, Any]: ...
    def serve_restored_predecessor(self, activation: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class TransitionStageExecutionContext:
    """Immutable, request-local custody for subordinate approval artifacts."""

    requested_stage: str
    subordinate_approvals: tuple[Mapping[str, Any], ...]

    @classmethod
    def create(cls, requested_stage: str,
               approvals: Sequence[Mapping[str, Any]]) -> "TransitionStageExecutionContext":
        frozen = tuple(MappingProxyType(_plain(item)) for item in approvals)
        return cls(requested_stage=requested_stage, subordinate_approvals=frozen)

    def exact_activation_approval(self) -> Mapping[str, Any]:
        if self.requested_stage not in {"b_activation_committed", "a_restoration_activation_committed"}:
            raise TransitionError("activation_approval_requested_for_wrong_stage")
        if len(self.subordinate_approvals) != 1:
            raise TransitionError("exact_external_activation_approval_required")
        approval = self.subordinate_approvals[0]
        if not approval.get("approval_evidence_id") or not approval.get("approval_semantic_digest"):
            raise TransitionError("exact_external_activation_approval_required")
        return approval


def make_stage_approval(*, protocol: TransitionProtocol, requested_stage: str, prior_phase: str,
                        journal_head_digest: str, correlation_id: str,
                        current_activation: Mapping[str, Any] | None,
                        current_session: Mapping[str, Any] | None,
                        current_boundary: Mapping[str, Any] | None,
                        synthetic_test_approval: bool, not_before: str, expires_at: str) -> Mapping[str, Any]:
    body = {"schema_version": APPROVAL_SCHEMA, "approval_status": "approved", "capability": CAPABILITY,
            "principal": PRINCIPAL, "protocol_id": protocol.value["protocol_id"],
            "protocol_digest": protocol.value["protocol_digest"], "transition_id": protocol.value["transition_id"],
            "requested_stage": requested_stage, "prior_phase": prior_phase,
            "journal_head_digest": journal_head_digest,
            "installation_identity": protocol.value["installation_identity"],
            "predecessor_identity": _plain(protocol.value["predecessor_a"]),
            "successor_identity": _plain(protocol.value["successor_b"]),
            "restored_identity": _plain(protocol.value["restored_a"]),
            "current_activation": _plain(current_activation), "current_session": _plain(current_session),
            "current_boundary": _plain(current_boundary), "correlation_id": correlation_id,
            "operation_identity": (protocol.value["b_serving_operation_id"] if requested_stage == "b_serving_bound"
                                   else protocol.value["restored_a_serving_operation_id"]
                                   if requested_stage == "restored_a_serving_bound" else correlation_id),
            "not_before": not_before, "expires_at": expires_at,
            "synthetic_test_approval": synthetic_test_approval,
            "grants_activation": False, "grants_model_serving": False, "grants_inference": False}
    return MappingProxyType({**body, "approval_digest": digest(body)})


def verify_stage_approval(approval: Mapping[str, Any], *, expected: Mapping[str, Any],
                          observation_time: datetime, allow_synthetic_for_tests: bool) -> None:
    value = dict(approval)
    claimed = value.pop("approval_digest", None)
    if value.get("schema_version") != APPROVAL_SCHEMA or digest(value) != claimed:
        raise TransitionError("stage_approval_tamper")
    for key, expected_value in expected.items():
        if value.get(key) != _plain(expected_value):
            raise TransitionError("stage_approval_binding_mismatch")
    try:
        start = datetime.fromisoformat(str(value["not_before"]).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(value["expires_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise TransitionError("stage_approval_validity_invalid") from exc
    now = observation_time.astimezone(timezone.utc)
    if not start <= now <= end:
        raise TransitionError("stage_approval_not_current")
    if value.get("synthetic_test_approval") is True and not allow_synthetic_for_tests:
        raise TransitionError("synthetic_stage_approval_forbidden")
    if any(value.get(key) is not False for key in ("grants_activation", "grants_model_serving", "grants_inference")):
        raise TransitionError("stage_approval_grants_subordinate_authority")


@dataclass(frozen=True)
class _Reconstructed:
    phase: str
    blocked: bool
    reason: str | None
    outstanding_stage: str | None
    token: Mapping[str, Any] | None
    semantically_verified_stage_entry_digests: tuple[str, ...] = ()


class ResidentCognitiveModelTransitionController:
    """Advance one approved stage through exact subordinate operation methods."""
    def __init__(self, *, protocol: TransitionProtocol, journal: TransitionJournal,
                 gate: ResidentCognitionQuiescenceGate, slot: Any,
                 history_snapshot: Any, operations: TransitionStageOperations | None = None,
                 allow_synthetic_approval_for_tests: bool = False,
                 clock: Any = lambda: datetime.now(timezone.utc)):
        protocol.verify()
        self.protocol, self.journal, self.gate, self.slot = protocol, journal, gate, slot
        self.history_snapshot, self.operations = history_snapshot, operations
        self.allow_synthetic_approval_for_tests, self.clock = allow_synthetic_approval_for_tests, clock
        self._state = self._reconstruct()

    def _completed_stage_evidence_error(self, stage: str, evidence: Mapping[str, Any],
                                        prior_activation: Mapping[str, Any] | None) -> str | None:
        activation_stages = {"b_activation_committed": ("successor_b", "A->B"),
                             "a_restoration_activation_committed": ("restored_a", "B->A")}
        serving_stages = {"b_serving_bound": ("successor_b", "b_serving_operation_id"),
                          "restored_a_serving_bound": ("restored_a", "restored_a_serving_operation_id")}
        if stage in activation_stages:
            role, marker = activation_stages[stage]
            activation = evidence.get("activation")
            expected = self.protocol.value.get(role)
            if not isinstance(activation, Mapping) or not isinstance(expected, Mapping):
                return "activation_stage_evidence_missing"
            if (evidence.get("activation_transition_stage") != marker
                    or activation.get("model_loaded") is not False
                    or activation.get("serving_started") is not False
                    or activation.get("inference_performed") is not False
                    or not isinstance(activation.get("state_semantic_digest"), str)
                    or not isinstance(activation.get("receipt_id"), str)
                    or not isinstance(activation.get("receipt_semantic_digest"), str)
                    or not isinstance(activation.get("activation_history_digest"), str)
                    or activation.get("commissioning_active_model_identity") != expected.get("active_model_identity")):
                return "activation_stage_identity_mismatch"
            verifier = getattr(self.operations, "verify_historical_activation", None)
            if not callable(verifier):
                return "activation_history_verifier_unavailable"
            try:
                verified_identity = verifier(activation)
            except Exception:
                return "activation_history_lineage_unverified"
            if not isinstance(verified_identity, Mapping) or dict(verified_identity) != expected.get("active_model_identity"):
                return "activation_commissioning_identity_mismatch"
            return None
        if stage in serving_stages:
            if not isinstance(prior_activation, Mapping):
                return "serving_stage_activation_predecessor_missing"
            role, operation_key = serving_stages[stage]
            expected = self.protocol.value.get(role)
            binding, session = evidence.get("stage_binding"), evidence.get("session")
            if not isinstance(expected, Mapping) or not isinstance(binding, Mapping) or not isinstance(session, Mapping):
                return "serving_stage_evidence_missing"
            binding_body = dict(binding)
            claimed_binding_digest = binding_body.pop("binding_digest", None)
            if (binding.get("schema_version") != BINDING_SCHEMA
                    or digest(binding_body) != claimed_binding_digest
                    or binding.get("protocol_id") != self.protocol.value.get("protocol_id")
                    or binding.get("protocol_digest") != self.protocol.value.get("protocol_digest")
                    or binding.get("transition_id") != self.protocol.value.get("transition_id")
                    or binding.get("stage") != stage
                    or binding.get("installation_identity") != self.protocol.value.get("installation_identity")
                    or binding.get("expected_model_identity") != _plain(expected)
                    or binding.get("serving_operation_id") != self.protocol.value.get(operation_key)
                    or binding.get("activation_state_digest") != prior_activation.get("state_semantic_digest")
                    or binding.get("activation_generation") != prior_activation.get("generation")
                    or binding.get("activation_receipt_id") != prior_activation.get("receipt_id")
                    or binding.get("activation_receipt_digest") != prior_activation.get("receipt_semantic_digest")
                    or binding.get("activation_history_digest") != prior_activation.get("activation_history_digest")
                    or any(binding.get(key) is not False for key in ("grants_activation", "grants_model_serving", "grants_inference"))):
                return "serving_stage_binding_mismatch"
            session_id, session_binding = session.get("session_id"), session.get("binding")
            if not isinstance(session_binding, Mapping):
                return "serving_stage_session_binding_missing"
            receipt_verifier = getattr(self.operations, "verify_historical_serving_session", None)
            if not callable(receipt_verifier):
                return "serving_receipt_verifier_unavailable"
            try:
                serving_receipt = receipt_verifier(session)
            except Exception:
                return "serving_receipt_unverified"
            if (serving_receipt.get("receipt_id") != evidence.get("serving_receipt_id")
                    or serving_receipt.get("receipt_semantic_digest")
                    != evidence.get("serving_receipt_semantic_digest")):
                return "serving_receipt_binding_mismatch"
            activation_state = {key: value for key, value in prior_activation.items()
                if key not in {"receipt_id", "receipt_semantic_digest", "activation_history_digest",
                               "commissioning_active_model_identity", "activation_transition_stage"}}
            if (session_id != "resident-serving-session-" + semantic_digest(dict(session_binding))[:24]
                    or session.get("status") != "production_current"
                    or session_binding.get("installation_identity") != binding.get("installation_identity")
                    or session_binding.get("serving_operation_id") != binding.get("serving_operation_id")
                    or session_binding.get("activation_state_semantic_digest") != prior_activation.get("state_semantic_digest")
                    or session_binding.get("activation_generation") != prior_activation.get("generation")
                    or session_binding.get("activation_receipt_id") != prior_activation.get("receipt_id")
                    or session_binding.get("activation_receipt_semantic_digest") != prior_activation.get("receipt_semantic_digest")
                    or session_binding.get("activation_history_digest") != prior_activation.get("activation_history_digest")
                    or session_binding.get("activation_state") != activation_state
                    or session_binding.get("observed_loaded_model_identity") != expected.get("active_model_identity")
                    or session_binding.get("model_serving_admission_ref") != evidence.get("serving_admission")):
                return "serving_stage_session_mismatch"
            return None
        if stage in {"b_epoch_observed", "post_restoration_observed"}:
            verifier = getattr(self.operations, "verify_transition_observation", None)
            if not callable(verifier):
                return "transition_observation_verifier_unavailable"
            try:
                verifier(stage, evidence)
            except Exception:
                return "transition_observation_lineage_unverified"
            return None
        return None

    def _reconstruct(self) -> _Reconstructed:
        phase, outstanding, token = PHASES[0], None, None
        blocked, reason = False, None
        semantically_verified: list[str] = []
        latest_activation: Mapping[str, Any] | None = None
        latest_serving_session_id: str | None = None
        for entry in self.journal.entries():
            status, entry_phase, evidence = entry["status"], entry["phase"], entry["evidence"]
            if status == "attempted":
                if blocked or outstanding or entry_phase != phase or evidence.get("attempted_stage") != PHASES[PHASES.index(phase)+1]:
                    raise TransitionError("journal_stage_order_invalid")
                outstanding = str(evidence["attempted_stage"])
            elif status == "completed":
                expected = PHASES[PHASES.index(phase)+1] if phase != PHASES[-1] else None
                if entry_phase != expected or (outstanding is not None and outstanding != entry_phase):
                    raise TransitionError("journal_stage_order_invalid")
                failure = self._completed_stage_evidence_error(entry_phase, evidence, latest_activation)
                if failure is not None:
                    return _Reconstructed(entry_phase, True, failure, entry_phase, token,
                        tuple(semantically_verified[-128:]))
                semantically_verified.append(str(entry.get("entry_digest")))
                if entry_phase in {"b_activation_committed", "a_restoration_activation_committed"}:
                    latest_activation = evidence.get("activation")
                    latest_serving_session_id = None
                elif entry_phase in {"b_serving_bound", "restored_a_serving_bound"}:
                    session_value = evidence.get("session")
                    latest_serving_session_id = (session_value.get("session_id")
                        if isinstance(session_value, Mapping) and isinstance(session_value.get("session_id"), str) else None)
                elif entry_phase in {"b_epoch_resumed", "restored_a_epoch_resumed"}:
                    if (latest_serving_session_id is None
                            or evidence.get("verified_session_id") != latest_serving_session_id):
                        return _Reconstructed(entry_phase, True, "resumed_session_binding_mismatch", entry_phase, token,
                            tuple(semantically_verified[-128:]))
                phase, outstanding = entry_phase, None
                token = evidence if entry_phase in {"a_quiesced", "b_quiesced"} else None if entry_phase in {"b_epoch_resumed", "restored_a_epoch_resumed"} else token
            elif status == "effected":
                if outstanding != entry_phase or entry_phase not in EFFECTFUL or not evidence.get("subordinate_custody_verified"):
                    raise TransitionError("journal_effect_custody_invalid")
                phase, blocked, reason = entry_phase, True, "effected_completion_evidence_missing"
                outstanding = entry_phase
            elif status in {"failed", "interrupted"}:
                if evidence.get("failed_stage") != outstanding and evidence.get("interrupted_stage") != outstanding:
                    raise TransitionError("journal_failure_binding_invalid")
                blocked, reason = True, status
            else:
                raise TransitionError("journal_tamper")
        if outstanding is not None:
            blocked, reason = True, reason or "unresolved_attempt"
        if token is not None and not self.gate.verifies(token):
            blocked, reason = True, "live_quiescence_custody_mismatch"
        return _Reconstructed(phase, blocked, reason, outstanding, token,
            tuple(semantically_verified[-128:]))

    @property
    def phase(self) -> str:
        return self._state.phase

    def _approval_expected(self, target: str, approval: Mapping[str, Any]) -> Mapping[str, Any]:
        boundary = _plain(self.history_snapshot())
        return {"capability": CAPABILITY, "principal": PRINCIPAL,
                "protocol_id": self.protocol.value["protocol_id"],
                "protocol_digest": self.protocol.value["protocol_digest"],
                "transition_id": self.protocol.value["transition_id"], "requested_stage": target,
                "prior_phase": self.phase, "journal_head_digest": (self.journal.entries()[-1]["entry_digest"]
                                                                    if self.journal.entries() else "GENESIS"),
                "installation_identity": self.protocol.value["installation_identity"],
                "predecessor_identity": self.protocol.value["predecessor_a"],
                "successor_identity": self.protocol.value["successor_b"],
                "restored_identity": self.protocol.value["restored_a"],
                "current_activation": boundary.get("current_activation"),
                "current_session": boundary.get("current_resident_serving_session"),
                "current_boundary": boundary,
                "correlation_id": approval.get("correlation_id"),
                "operation_identity": approval.get("operation_identity")}

    def advance(self, *, approval: Mapping[str, Any], evidence: Mapping[str, Any] | None = None,
                stage_execution_context: TransitionStageExecutionContext | None = None,
                operation_context: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        if os.name != "posix":
            raise TransitionError("model_transition_unsupported_platform")
        self.protocol.verify()
        self._state = self._reconstruct()
        if self._state.blocked:
            raise TransitionError("failed_or_unresolved_stage_replay_forbidden")
        if self.phase == PHASES[-1]:
            raise TransitionError("experiment_already_complete")
        current = self.phase
        target = PHASES[PHASES.index(current) + 1]
        verify_stage_approval(approval, expected=self._approval_expected(target, approval),
                              observation_time=self.clock(), allow_synthetic_for_tests=self.allow_synthetic_approval_for_tests)
        supplied = dict(evidence or {})
        context = dict(operation_context or {})
        if context and (set(context) != {"request_id", "request_digest"}
                        or not all(isinstance(value, str) and value for value in context.values())):
            raise TransitionError("transition_operation_context_invalid")
        # Publish an attempt before any stage can mutate runtime state. This
        # makes a crash between a non-effectful handoff and its completion
        # distinguishable from a request that was never admitted.
        self.journal.append(current, {"attempted_stage": target,
                                      "approval_digest": approval["approval_digest"],
                                      **({"operator_request": context} if context else {})}, status="attempted")
        completion_published = False
        try:
            if target in {"a_quiesced", "b_quiesced"}:
                supplied = dict(self.gate.quiesce(timeout_seconds=float(supplied.pop("timeout_seconds", 5)),
                                                  observation={**_plain(self.history_snapshot()), **supplied}))
            elif target in {"b_epoch_resumed", "restored_a_epoch_resumed"}:
                if self._state.token is None or not self.gate.verifies(self._state.token):
                    raise TransitionError("resume_without_verified_live_quiescence")
                expected_identity = (self.protocol.value["successor_b"] if target == "b_epoch_resumed"
                                     else self.protocol.value["restored_a"])
                session = self.slot.current_controller.current_session()
                if session is None or _plain(session.binding["observed_loaded_model_identity"]) != _plain(expected_identity):
                    raise TransitionError("resume_serving_identity_mismatch")
                self.gate.resume(self._state.token)
                supplied.update({"verified_session_id": session.session_id})
            elif target == "b_activation_committed":
                if self.operations is None: raise TransitionError("transition_operations_required")
                supplied.update(_plain(self.operations.activate_successor(stage_execution_context)))
            elif target == "b_serving_bound":
                if self.operations is None: raise TransitionError("transition_operations_required")
                activation = next(entry["evidence"]["activation"] for entry in reversed(self.journal.entries())
                                  if entry["status"] == "completed" and entry["phase"] == "b_activation_committed")
                supplied.update(_plain(self.operations.serve_successor(activation)))
            elif target == "a_restoration_activation_committed":
                if self.operations is None: raise TransitionError("transition_operations_required")
                supplied.update(_plain(self.operations.activate_restored_predecessor(stage_execution_context)))
            elif target == "restored_a_serving_bound":
                if self.operations is None: raise TransitionError("transition_operations_required")
                activation = next(entry["evidence"]["activation"] for entry in reversed(self.journal.entries())
                                  if entry["status"] == "completed" and entry["phase"] == "a_restoration_activation_committed")
                supplied.update(_plain(self.operations.serve_restored_predecessor(activation)))
            if target in {"b_epoch_observed", "post_restoration_observed"}:
                verifier = getattr(self.operations, "verify_transition_observation", None)
                if not callable(verifier):
                    raise TransitionError("transition_observation_verifier_unavailable")
                verifier(target, supplied)
            if context:
                supplied["operator_request"] = context
            entry = self.journal.append(target, supplied)
            completion_published = True
            self._state = self._reconstruct()
            return MappingProxyType({"prior_phase": current, "phase": target,
                                     "journal_head": entry["entry_digest"], "advanced_one_stage": True})
        except Exception as exc:
            # A completed journal row is the durable commit point. Do not
            # append a contradictory failure if a later in-memory refresh
            # fails; restart recovery will reconstruct from that completion.
            if not completion_published:
                self.journal.append(current, {"failed_stage": target,
                                              "error": getattr(exc, "code", type(exc).__name__),
                                              **({"operator_request": context} if context else {})}, status="failed")
                self._state = self._reconstruct()
            raise

    def health(self) -> Mapping[str, Any]:
        self._state = self._reconstruct()
        entries = self.journal.entries()
        status = "interrupted" if self._state.blocked else "complete" if self.phase == PHASES[-1] else "in_progress"
        return MappingProxyType({"schema_version": "sentientos.resident_cognitive_model_transition_health:v1",
                                 "status": status, "phase": self.phase, "reason": self._state.reason,
                                 "outstanding_stage": self._state.outstanding_stage,
                                 "replay_forbidden": self._state.blocked,
                                 "quiesced": self.gate.quiesced,
                                 "journal_head": entries[-1]["entry_digest"] if entries else "GENESIS",
                                 "semantically_verified_stage_entry_digests": list(
                                     self._state.semantically_verified_stage_entry_digests),
                                 "read_only": True})
