"""Standalone custody for governed local-model call entitlements.

This module deliberately has no dependency on model invocation, serving, or the
control plane.  A future composition layer may call :meth:`final_gate` only after
independent effect admission and immediately before the serving-currentness guard.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Any, Mapping

from sentientos.causal_resource_principal import CausalResourcePrincipal, CausalResourcePrincipalVerifier
from sentientos.causal_resource_principal_authentication import AuthenticatedRootPrincipalEvidence
from sentientos.causal_resource_principal_currentness import CurrentAuthenticatedRootPrincipalEvidence

RESOURCE_KIND = "governed_local_model_invocation_call_entitlement.v1"
ALLOCATOR_ID = "sentientos.governed_local_model_resource_allocator.v1"
POLICY_SCHEMA = "sentientos.governed_local_model_resource_policy:v1"
LEDGER_SCHEMA = "sentientos.governed_local_model_resource_ledger:v1"
ALLOCATION_SCHEMA = "sentientos.governed_local_model_resource_allocation:v1"
RECEIPT_SCHEMA = "sentientos.governed_local_model_resource_consumption_receipt:v1"
_HEX = re.compile(r"[0-9a-f]{64}")


class GovernedLocalModelResourceError(ValueError):
    """A closed resource record or custody transition failed verification."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                          allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise GovernedLocalModelResourceError("noncanonical_json") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _closed(value: Mapping[str, object], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise GovernedLocalModelResourceError(f"{label}_fields_not_exact")


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise GovernedLocalModelResourceError("duplicate_json_key")
        result[key] = value
    return result


def _load_json(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_object_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(GovernedLocalModelResourceError("nonfinite_json")))
    except (OSError, json.JSONDecodeError) as exc:
        raise GovernedLocalModelResourceError("malformed_json") from exc
    if not isinstance(value, dict):
        raise GovernedLocalModelResourceError("json_object_required")
    return value


def _time(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise GovernedLocalModelResourceError(f"invalid_{label}")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise GovernedLocalModelResourceError(f"invalid_{label}") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed) or parsed.isoformat(timespec="seconds").replace("+00:00", "Z") != value:
        raise GovernedLocalModelResourceError(f"noncanonical_{label}")
    return parsed


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or _HEX.fullmatch(value) is None:
        raise GovernedLocalModelResourceError(f"invalid_{label}")
    return value


@dataclass(frozen=True, slots=True)
class GovernedLocalModelResourceBounds:
    max_input_chars: int
    max_output_chars: int
    max_new_tokens: int
    timeout_seconds: float
    max_calls_per_correlation: int

    def __post_init__(self) -> None:
        for name in ("max_input_chars", "max_output_chars", "max_new_tokens", "max_calls_per_correlation"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise GovernedLocalModelResourceError(f"invalid_{name}")
        if type(self.timeout_seconds) not in (int, float) or isinstance(self.timeout_seconds, bool) or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise GovernedLocalModelResourceError("invalid_timeout_seconds")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "GovernedLocalModelResourceBounds":
        _closed(value, set(cls.__dataclass_fields__), "bounds")
        return cls(**dict(value))  # type: ignore[arg-type]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GovernedLocalModelResourcePolicy:
    schema: str
    allocator_id: str
    epoch: int
    resource_kind: str
    max_resource_specific_bounds: GovernedLocalModelResourceBounds
    not_before: str
    valid_until: str
    policy_digest: str

    @classmethod
    def create(cls, *, epoch: int, max_resource_specific_bounds: GovernedLocalModelResourceBounds,
               not_before: str, valid_until: str) -> "GovernedLocalModelResourcePolicy":
        body: dict[str, object] = {"schema": POLICY_SCHEMA, "allocator_id": ALLOCATOR_ID, "epoch": epoch,
            "resource_kind": RESOURCE_KIND, "max_resource_specific_bounds": max_resource_specific_bounds.to_dict(),
            "not_before": not_before, "valid_until": valid_until}
        return cls.from_mapping({**body, "policy_digest": _digest(body)})

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "GovernedLocalModelResourcePolicy":
        _closed(value, set(cls.__dataclass_fields__), "policy")
        if value["schema"] != POLICY_SCHEMA or value["allocator_id"] != ALLOCATOR_ID or value["resource_kind"] != RESOURCE_KIND:
            raise GovernedLocalModelResourceError("policy_identity_mismatch")
        if type(value["epoch"]) is not int or value["epoch"] < 1:
            raise GovernedLocalModelResourceError("invalid_policy_epoch")
        bounds_value = value["max_resource_specific_bounds"]
        if not isinstance(bounds_value, Mapping):
            raise GovernedLocalModelResourceError("invalid_policy_bounds")
        before, until = _time(value["not_before"], "policy_not_before"), _time(value["valid_until"], "policy_valid_until")
        if until <= before:
            raise GovernedLocalModelResourceError("invalid_policy_validity")
        claimed = _sha(value["policy_digest"], "policy_digest")
        body = dict(value); body.pop("policy_digest")
        if claimed != _digest(body):
            raise GovernedLocalModelResourceError("policy_digest_mismatch")
        return cls(schema=POLICY_SCHEMA, allocator_id=ALLOCATOR_ID, epoch=value["epoch"], resource_kind=RESOURCE_KIND,
                   max_resource_specific_bounds=GovernedLocalModelResourceBounds.from_mapping(bounds_value),
                   not_before=value["not_before"], valid_until=value["valid_until"], policy_digest=claimed)  # type: ignore[arg-type]

    @classmethod
    def load(cls, path: str | Path, *, expected_policy_digest: str) -> "GovernedLocalModelResourcePolicy":
        policy = cls.from_mapping(_load_json(Path(path)))
        if policy.policy_digest != _sha(expected_policy_digest, "expected_policy_digest"):
            raise GovernedLocalModelResourceError("unexpected_policy_digest")
        return policy

    def to_dict(self) -> dict[str, object]:
        result = asdict(self); result["max_resource_specific_bounds"] = self.max_resource_specific_bounds.to_dict(); return result


@dataclass(frozen=True, slots=True)
class GovernedLocalModelAllocationValidity:
    not_before: str
    not_after: str
    principal_currentness_checked_at: str
    principal_currentness_valid_until: str
    allocator_policy_valid_until: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "GovernedLocalModelAllocationValidity":
        _closed(value, set(cls.__dataclass_fields__), "validity")
        for field in cls.__dataclass_fields__: _time(value[field], field)
        return cls(**dict(value))  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class GovernedLocalModelResourceAllocation:
    allocation_id: str
    principal_binding_digest: str
    principal_id: str
    principal_epoch: int
    resource_kind: str
    resource_specific_bounds: GovernedLocalModelResourceBounds
    validity: GovernedLocalModelAllocationValidity
    allocator_id: str
    epoch: int
    policy_digest: str
    allocation_digest: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "GovernedLocalModelResourceAllocation":
        _closed(value, set(cls.__dataclass_fields__), "allocation")
        bounds, validity = value["resource_specific_bounds"], value["validity"]
        if not isinstance(bounds, Mapping) or not isinstance(validity, Mapping):
            raise GovernedLocalModelResourceError("malformed_allocation")
        if value["resource_kind"] != RESOURCE_KIND or value["allocator_id"] != ALLOCATOR_ID:
            raise GovernedLocalModelResourceError("allocation_identity_mismatch")
        if type(value["principal_epoch"]) is not int or value["principal_epoch"] < 1 or type(value["epoch"]) is not int or value["epoch"] < 1:
            raise GovernedLocalModelResourceError("invalid_allocation_epoch")
        _sha(value["principal_binding_digest"].removeprefix("sha256:") if isinstance(value["principal_binding_digest"], str) else value["principal_binding_digest"], "principal_binding_digest")
        claimed = _sha(value["allocation_digest"], "allocation_digest")
        body = dict(value); body.pop("allocation_id"); body.pop("allocation_digest")
        if claimed != _digest(body): raise GovernedLocalModelResourceError("allocation_digest_mismatch")
        if value["allocation_id"] != "lmalloc-" + claimed[:24]: raise GovernedLocalModelResourceError("allocation_id_mismatch")
        if not isinstance(value["allocation_id"], str) or not isinstance(value["principal_binding_digest"], str) or not isinstance(value["principal_id"], str):
            raise GovernedLocalModelResourceError("malformed_allocation_identity")
        return cls(allocation_id=value["allocation_id"], principal_binding_digest=value["principal_binding_digest"],
                   principal_id=value["principal_id"], principal_epoch=value["principal_epoch"], resource_kind=RESOURCE_KIND,
                   resource_specific_bounds=GovernedLocalModelResourceBounds.from_mapping(bounds),
                   validity=GovernedLocalModelAllocationValidity.from_mapping(validity), allocator_id=ALLOCATOR_ID,
                   epoch=value["epoch"], policy_digest=_sha(value["policy_digest"], "policy_digest"), allocation_digest=claimed)

    def to_dict(self) -> dict[str, object]: return asdict(self)


_MEASUREMENT_FIELDS = {"generation_attempted", "call_units_consumed", "generated_output_size_bytes",
 "returned_output_size_bytes", "output_truncated", "latency_ms", "configured_bounds", "invocation_outcome", "actual_token_count"}
_STATES = {"attempted_not_begun", "attempt_begun", "measured_completed", "measured_timeout", "measured_backend_failure", "reconciled"}


@dataclass(frozen=True, slots=True)
class GovernedLocalModelResourceConsumptionReceipt:
    receipt_id: str
    allocation_digest: str
    principal_binding_digest: str
    attempt_id: str
    resource_specific_measurement: Mapping[str, object]
    state: str
    observed_at: str
    previous_receipt_digest: str | None
    effect_receipt_digest: str | None
    receipt_digest: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "GovernedLocalModelResourceConsumptionReceipt":
        _closed(value, set(cls.__dataclass_fields__), "receipt")
        measurement = value["resource_specific_measurement"]
        if not isinstance(measurement, Mapping): raise GovernedLocalModelResourceError("malformed_measurement")
        _closed(measurement, _MEASUREMENT_FIELDS, "measurement")
        if measurement["actual_token_count"] is not None: raise GovernedLocalModelResourceError("actual_token_count_untrusted")
        if type(measurement["generation_attempted"]) is not bool or type(measurement["call_units_consumed"]) is not int or measurement["call_units_consumed"] not in (0, 1):
            raise GovernedLocalModelResourceError("invalid_measurement")
        configured = measurement["configured_bounds"]
        if not isinstance(configured, Mapping): raise GovernedLocalModelResourceError("invalid_configured_bounds")
        GovernedLocalModelResourceBounds.from_mapping(configured)
        if value["state"] not in _STATES: raise GovernedLocalModelResourceError("invalid_receipt_state")
        _time(value["observed_at"], "observed_at")
        for field in ("allocation_digest", "receipt_digest"):
            _sha(value[field], field)
        for field in ("previous_receipt_digest", "effect_receipt_digest"):
            if value[field] is not None: _sha(value[field], field)
        body = dict(value); body.pop("receipt_id"); body.pop("receipt_digest")
        claimed = value["receipt_digest"]
        if claimed != _digest(body): raise GovernedLocalModelResourceError("receipt_digest_mismatch")
        if value["receipt_id"] != "lmresrec-" + claimed[:24]: raise GovernedLocalModelResourceError("receipt_id_mismatch")
        return cls(**dict(value))  # type: ignore[arg-type]

    def to_dict(self) -> dict[str, object]: return asdict(self)


@dataclass(frozen=True, slots=True)
class GovernedLocalModelResourceLedgerObservation:
    """Validated immutable view of ledger bytes; it owns no allocation or write capability."""

    _snapshot: Mapping[str, object]

    def observation_snapshot(self) -> Mapping[str, object]:
        return {
            "schema": self._snapshot["schema"],
            "ledger_digest": self._snapshot["ledger_digest"],
            "allocations": tuple(dict(item) for item in self._snapshot["allocations"]),
            "attempts": tuple(dict(item) for item in self._snapshot["attempts"]),
            "receipts": tuple(dict(item) for item in self._snapshot["receipts"]),
        }


class GovernedLocalModelResourceLedger:
    """Single-process, digest-sealed, atomically replaced ledger custody."""
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path); self._lock = threading.RLock()
        if self.path.exists(): self._state = self._read()
        else:
            self._state = {"schema": LEDGER_SCHEMA, "allocations": {}, "attempts": {}, "receipts": []}
            self._persist()

    def _body(self) -> dict[str, object]: return dict(self._state)
    def _read(self) -> dict[str, Any]:
        raw = _load_json(self.path); _closed(raw, {"schema", "allocations", "attempts", "receipts", "ledger_digest"}, "ledger")
        body = dict(raw); claimed = body.pop("ledger_digest")
        if raw["schema"] != LEDGER_SCHEMA or claimed != _digest(body): raise GovernedLocalModelResourceError("ledger_digest_mismatch")
        if not isinstance(raw["allocations"], dict) or not isinstance(raw["attempts"], dict) or not isinstance(raw["receipts"], list): raise GovernedLocalModelResourceError("malformed_ledger")
        for key, item in raw["allocations"].items():
            if not isinstance(item, Mapping) or GovernedLocalModelResourceAllocation.from_mapping(item).allocation_id != key: raise GovernedLocalModelResourceError("malformed_ledger_allocation")
        state = body
        self._verify_invariants(state)
        return state

    @classmethod
    def read_only_snapshot(cls, raw_bytes: bytes, *, max_bytes: int = 8 * 1024 * 1024) -> GovernedLocalModelResourceLedgerObservation:
        """Validate one bounded atomic ledger image without opening mutable ledger custody."""
        if type(raw_bytes) is not bytes or type(max_bytes) is not int or max_bytes < 1:
            raise GovernedLocalModelResourceError("invalid_read_only_ledger_input")
        if len(raw_bytes) > max_bytes:
            raise GovernedLocalModelResourceError("ledger_size_bound_exceeded")
        try:
            raw = json.loads(raw_bytes.decode("utf-8"), object_pairs_hook=_object_pairs,
                             parse_constant=lambda _: (_ for _ in ()).throw(GovernedLocalModelResourceError("nonfinite_json")))
        except GovernedLocalModelResourceError:
            raise
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise GovernedLocalModelResourceError("malformed_json") from exc
        if not isinstance(raw, dict):
            raise GovernedLocalModelResourceError("json_object_required")
        _closed(raw, {"schema", "allocations", "attempts", "receipts", "ledger_digest"}, "ledger")
        body = dict(raw)
        claimed = body.pop("ledger_digest")
        if raw["schema"] != LEDGER_SCHEMA or claimed != _digest(body):
            raise GovernedLocalModelResourceError("ledger_digest_mismatch")
        allocations, attempts, receipts = raw["allocations"], raw["attempts"], raw["receipts"]
        if not isinstance(allocations, dict) or not isinstance(attempts, dict) or not isinstance(receipts, list):
            raise GovernedLocalModelResourceError("malformed_ledger")
        for key, item in allocations.items():
            if not isinstance(item, Mapping) or GovernedLocalModelResourceAllocation.from_mapping(item).allocation_id != key:
                raise GovernedLocalModelResourceError("malformed_ledger_allocation")
        cls._verify_invariants(body)
        snapshot = {
            "schema": LEDGER_SCHEMA, "ledger_digest": claimed,
            "allocations": tuple(dict(item) for item in allocations.values()),
            "attempts": tuple({"attempt_id": key, **dict(value)} for key, value in sorted(attempts.items())),
            "receipts": tuple(dict(item) for item in receipts),
        }
        return GovernedLocalModelResourceLedgerObservation(snapshot)

    @staticmethod
    def _verify_invariants(state: Mapping[str, object]) -> None:
        allocations = state["allocations"]; attempts = state["attempts"]; receipts = state["receipts"]
        assert isinstance(allocations, dict) and isinstance(attempts, dict) and isinstance(receipts, list)
        seen: dict[str, str] = {}
        for item in receipts:
            if not isinstance(item, Mapping): raise GovernedLocalModelResourceError("malformed_ledger_receipt")
            receipt = GovernedLocalModelResourceConsumptionReceipt.from_mapping(item)
            expected = seen.get(receipt.attempt_id)
            if receipt.previous_receipt_digest != expected: raise GovernedLocalModelResourceError("broken_receipt_predecessor")
            seen[receipt.attempt_id] = receipt.receipt_digest
        for allocation_id, item in allocations.items():
            allocation = GovernedLocalModelResourceAllocation.from_mapping(item)
            debits = sum(1 for attempt in attempts.values() if isinstance(attempt, dict) and attempt.get("allocation_id") == allocation_id and attempt.get("status") in {"provisional", "begun"})
            if debits > allocation.resource_specific_bounds.max_calls_per_correlation: raise GovernedLocalModelResourceError("negative_remaining_calls")
        for attempt_id, attempt in attempts.items():
            if not isinstance(attempt_id, str) or not attempt_id.startswith("lmattempt-") or not isinstance(attempt, dict):
                raise GovernedLocalModelResourceError("malformed_ledger_attempt")
            if set(attempt) != {"allocation_id", "status"} or attempt["allocation_id"] not in allocations or attempt["status"] not in {"provisional", "begun", "restored"}:
                raise GovernedLocalModelResourceError("malformed_ledger_attempt")

    def _persist_candidate(self, candidate: dict[str, Any]) -> None:
        """Publish a candidate before making it the process-local ledger state.

        If staging fails, the previous state remains active. Once atomic replace
        succeeds, retain the candidate even if directory fsync reports an error:
        publication durability is then uncertain, so rolling back in memory
        could replenish an entitlement already visible on disk.
        """
        self._verify_invariants(candidate)
        data = _canonical({**candidate, "ledger_digest": _digest(candidate)}) + b"\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            os.replace(name, self.path)
            self._state = candidate
            directory = os.open(self.path.parent, os.O_RDONLY)
            try: os.fsync(directory)
            finally: os.close(directory)
        finally:
            if os.path.exists(name): os.unlink(name)

    def _persist(self) -> None:
        self._persist_candidate(self._state)

    def _candidate(self) -> dict[str, Any]:
        return copy.deepcopy(self._state)

    def store_allocation(self, allocation: GovernedLocalModelResourceAllocation) -> None:
        with self._lock:
            if allocation.allocation_id in self._state["allocations"]: raise GovernedLocalModelResourceError("duplicate_allocation_id")
            candidate = self._candidate()
            candidate["allocations"][allocation.allocation_id] = allocation.to_dict()
            self._persist_candidate(candidate)

    def allocation(self, allocation_id: str) -> GovernedLocalModelResourceAllocation:
        try: value = self._state["allocations"][allocation_id]
        except KeyError as exc: raise GovernedLocalModelResourceError("allocation_not_stored") from exc
        return GovernedLocalModelResourceAllocation.from_mapping(value)

    def remaining_calls(self, allocation_id: str) -> int:
        allocation = self.allocation(allocation_id)
        used = sum(1 for value in self._state["attempts"].values() if value["allocation_id"] == allocation_id and value["status"] in {"provisional", "begun"})
        return allocation.resource_specific_bounds.max_calls_per_correlation - used

    def snapshot_counts(self) -> tuple[int, int, int]:
        """Return non-mutating allocation, attempt, and receipt counts."""
        with self._lock:
            return (len(self._state["allocations"]), len(self._state["attempts"]),
                    len(self._state["receipts"]))

    def observation_snapshot(self) -> Mapping[str, object]:
        """Return sealed ledger identities for a read-only causal observer."""
        with self._lock:
            self._verify_invariants(self._state)
            body = self._body()
            return {"schema": LEDGER_SCHEMA, "ledger_digest": _digest(body),
                    "allocations": tuple(body["allocations"].values()),
                    "attempts": tuple({"attempt_id": key, **value} for key, value in body["attempts"].items()),
                    "receipts": tuple(body["receipts"])}


class GovernedLocalModelResourceAllocator:
    def __init__(self, *, policy: GovernedLocalModelResourcePolicy, ledger: GovernedLocalModelResourceLedger) -> None:
        self.policy = GovernedLocalModelResourcePolicy.from_mapping(policy.to_dict()); self.ledger = ledger

    @staticmethod
    def _principal(principal: CausalResourcePrincipal, authenticated: AuthenticatedRootPrincipalEvidence,
                   current: CurrentAuthenticatedRootPrincipalEvidence, now: str) -> None:
        if type(principal) is not CausalResourcePrincipal or type(authenticated) is not AuthenticatedRootPrincipalEvidence or type(current) is not CurrentAuthenticatedRootPrincipalEvidence:
            raise GovernedLocalModelResourceError("verifier_created_principal_evidence_required")
        try: CausalResourcePrincipalVerifier().verify(principal, current_time=now)
        except ValueError as exc: raise GovernedLocalModelResourceError(str(exc)) from exc
        if not (principal.principal_id == authenticated.principal_id == current.principal_id): raise GovernedLocalModelResourceError("principal_id_mismatch")
        if not (principal.binding_digest == authenticated.principal_binding_digest == current.principal_binding_digest): raise GovernedLocalModelResourceError("principal_binding_mismatch")
        if not (principal.issuer_id == authenticated.issuer_id == current.issuer_id): raise GovernedLocalModelResourceError("principal_issuer_mismatch")
        if principal.epoch != current.epoch or authenticated.provenance_digest != current.provenance_digest: raise GovernedLocalModelResourceError("principal_epoch_or_provenance_mismatch")
        if _time(now, "current_time") >= _time(current.registry_valid_until, "registry_valid_until"): raise GovernedLocalModelResourceError("currentness_stale")

    def _policy_current(self, policy: GovernedLocalModelResourcePolicy, now: str) -> None:
        exact = GovernedLocalModelResourcePolicy.from_mapping(policy.to_dict())
        if exact != self.policy: raise GovernedLocalModelResourceError("policy_substitution")
        instant = _time(now, "current_time")
        if instant < _time(exact.not_before, "policy_not_before"): raise GovernedLocalModelResourceError("policy_not_yet_valid")
        if instant >= _time(exact.valid_until, "policy_valid_until"): raise GovernedLocalModelResourceError("policy_expired")

    def issue(self, *, principal: CausalResourcePrincipal, authenticated: AuthenticatedRootPrincipalEvidence,
              current: CurrentAuthenticatedRootPrincipalEvidence, requested_bounds: GovernedLocalModelResourceBounds,
              requested_not_before: str, requested_not_after: str, current_time: str) -> GovernedLocalModelResourceAllocation:
        self._principal(principal, authenticated, current, current_time); self._policy_current(self.policy, current_time)
        for name in GovernedLocalModelResourceBounds.__dataclass_fields__:
            if getattr(requested_bounds, name) > getattr(self.policy.max_resource_specific_bounds, name): raise GovernedLocalModelResourceError("requested_bounds_exceed_policy")
        before = max(_time(requested_not_before, "requested_not_before"), _time(principal.issued_at, "issued_at"), _time(self.policy.not_before, "policy_not_before"))
        after = min(_time(requested_not_after, "requested_not_after"), _time(principal.expires_at, "expires_at"), _time(current.registry_valid_until, "registry_valid_until"), _time(self.policy.valid_until, "policy_valid_until"))
        now = _time(current_time, "current_time")
        if not before <= now < after: raise GovernedLocalModelResourceError("allocation_not_current")
        validity = GovernedLocalModelAllocationValidity(before.isoformat(timespec="seconds").replace("+00:00", "Z"), after.isoformat(timespec="seconds").replace("+00:00", "Z"), current.checked_at, current.registry_valid_until, self.policy.valid_until)
        body: dict[str, object] = {"principal_binding_digest": principal.binding_digest, "principal_id": principal.principal_id,
            "principal_epoch": principal.epoch, "resource_kind": RESOURCE_KIND, "resource_specific_bounds": requested_bounds.to_dict(),
            "validity": asdict(validity), "allocator_id": ALLOCATOR_ID, "epoch": self.policy.epoch, "policy_digest": self.policy.policy_digest}
        digest = _digest(body)
        allocation = GovernedLocalModelResourceAllocation.from_mapping({"allocation_id": "lmalloc-" + digest[:24], **body, "allocation_digest": digest})
        self.ledger.store_allocation(allocation); return allocation

    def final_gate(self, *, allocation: GovernedLocalModelResourceAllocation, principal: CausalResourcePrincipal,
                   authenticated: AuthenticatedRootPrincipalEvidence, current: CurrentAuthenticatedRootPrincipalEvidence,
                   policy: GovernedLocalModelResourcePolicy, current_time: str, durable_attempt_nonce: str) -> str:
        self._principal(principal, authenticated, current, current_time); self._policy_current(policy, current_time)
        exact = GovernedLocalModelResourceAllocation.from_mapping(allocation.to_dict())
        if exact != self.ledger.allocation(exact.allocation_id): raise GovernedLocalModelResourceError("allocation_substitution")
        if (exact.principal_id, exact.principal_binding_digest, exact.principal_epoch) != (principal.principal_id, principal.binding_digest, principal.epoch): raise GovernedLocalModelResourceError("allocation_principal_mismatch")
        if exact.policy_digest != policy.policy_digest or exact.epoch != policy.epoch: raise GovernedLocalModelResourceError("allocation_policy_mismatch")
        now = _time(current_time, "current_time")
        if now < _time(exact.validity.not_before, "allocation_not_before") or now >= _time(exact.validity.not_after, "allocation_not_after"): raise GovernedLocalModelResourceError("allocation_expired")
        if not isinstance(durable_attempt_nonce, str) or not durable_attempt_nonce: raise GovernedLocalModelResourceError("invalid_durable_attempt_nonce")
        attempt_id = "lmattempt-" + _digest({"allocation_digest": exact.allocation_digest, "durable_attempt_nonce": durable_attempt_nonce})[:32]
        with self.ledger._lock:
            if attempt_id in self.ledger._state["attempts"]: raise GovernedLocalModelResourceError("duplicate_attempt_id")
            if self.ledger.remaining_calls(exact.allocation_id) <= 0: raise GovernedLocalModelResourceError("call_entitlement_exhausted")
            candidate = self.ledger._candidate()
            candidate["attempts"][attempt_id] = {
                "allocation_id": exact.allocation_id, "status": "provisional"}
            self.ledger._persist_candidate(candidate)
        return attempt_id

    def _receipt(self, *, allocation: GovernedLocalModelResourceAllocation, attempt_id: str, state: str,
                 observed_at: str, measurement: Mapping[str, object], effect_receipt_digest: str | None = None) -> GovernedLocalModelResourceConsumptionReceipt:
        with self.ledger._lock:
            attempt = self.ledger._state["attempts"].get(attempt_id)
            if attempt is None or attempt["allocation_id"] != allocation.allocation_id: raise GovernedLocalModelResourceError("attempt_allocation_mismatch")
            prior = next((r["receipt_digest"] for r in reversed(self.ledger._state["receipts"]) if r["attempt_id"] == attempt_id), None)
            body = {"allocation_digest": allocation.allocation_digest, "principal_binding_digest": allocation.principal_binding_digest,
                    "attempt_id": attempt_id, "resource_specific_measurement": dict(measurement), "state": state,
                    "observed_at": observed_at, "previous_receipt_digest": prior, "effect_receipt_digest": effect_receipt_digest}
            digest = _digest(body); receipt = GovernedLocalModelResourceConsumptionReceipt.from_mapping({"receipt_id": "lmresrec-" + digest[:24], **body, "receipt_digest": digest})
            candidate = self.ledger._candidate()
            candidate["receipts"].append(receipt.to_dict())
            self.ledger._persist_candidate(candidate)
            return receipt

    @staticmethod
    def measurement(allocation: GovernedLocalModelResourceAllocation, *, generation_attempted: bool,
                    call_units_consumed: int, generated_output_size_bytes: int | None = None,
                    returned_output_size_bytes: int | None = None, output_truncated: bool = False,
                    latency_ms: int | None = None, invocation_outcome: str) -> Mapping[str, object]:
        return {"generation_attempted": generation_attempted, "call_units_consumed": call_units_consumed,
                "generated_output_size_bytes": generated_output_size_bytes, "returned_output_size_bytes": returned_output_size_bytes,
                "output_truncated": output_truncated, "latency_ms": latency_ms,
                "configured_bounds": allocation.resource_specific_bounds.to_dict(), "invocation_outcome": invocation_outcome,
                "actual_token_count": None}

    def record_backend_entry(self, allocation: GovernedLocalModelResourceAllocation, attempt_id: str, *, observed_at: str) -> GovernedLocalModelResourceConsumptionReceipt:
        with self.ledger._lock:
            attempt = self.ledger._state["attempts"].get(attempt_id)
            if attempt is None or attempt["allocation_id"] != allocation.allocation_id: raise GovernedLocalModelResourceError("attempt_allocation_mismatch")
            if attempt["status"] != "provisional": raise GovernedLocalModelResourceError("backend_entry_transition_invalid")
            candidate = self.ledger._candidate()
            candidate["attempts"][attempt_id]["status"] = "begun"
            self.ledger._persist_candidate(candidate)
        return self._receipt(allocation=allocation, attempt_id=attempt_id, state="attempt_begun", observed_at=observed_at,
                             measurement=self.measurement(allocation, generation_attempted=True, call_units_consumed=1, invocation_outcome="backend_entry"))

    def reconcile_not_begun(self, allocation: GovernedLocalModelResourceAllocation, attempt_id: str, *, observed_at: str) -> GovernedLocalModelResourceConsumptionReceipt:
        with self.ledger._lock:
            attempt = self.ledger._state["attempts"].get(attempt_id)
            if attempt is None or attempt["allocation_id"] != allocation.allocation_id: raise GovernedLocalModelResourceError("attempt_allocation_mismatch")
            if attempt["status"] != "provisional": raise GovernedLocalModelResourceError("backend_entry_already_recorded")
            candidate = self.ledger._candidate()
            candidate["attempts"][attempt_id]["status"] = "restored"
            self.ledger._persist_candidate(candidate)
        return self._receipt(allocation=allocation, attempt_id=attempt_id, state="attempted_not_begun", observed_at=observed_at,
                             measurement=self.measurement(allocation, generation_attempted=False, call_units_consumed=0, invocation_outcome="serving_guard_rejected"))

    def append_receipt(self, allocation: GovernedLocalModelResourceAllocation, attempt_id: str, *, state: str,
                       observed_at: str, measurement: Mapping[str, object], effect_receipt_digest: str | None = None) -> GovernedLocalModelResourceConsumptionReceipt:
        if state == "attempted_not_begun": raise GovernedLocalModelResourceError("use_reconcile_not_begun")
        attempt = self.ledger._state["attempts"].get(attempt_id)
        if attempt is None or attempt["status"] != "begun": raise GovernedLocalModelResourceError("backend_entry_required")
        if measurement.get("generation_attempted") is not True or measurement.get("call_units_consumed") != 1: raise GovernedLocalModelResourceError("post_entry_consumption_required")
        return self._receipt(allocation=allocation, attempt_id=attempt_id, state=state, observed_at=observed_at,
                             measurement=measurement, effect_receipt_digest=effect_receipt_digest)


__all__ = ["ALLOCATOR_ID", "RESOURCE_KIND", "GovernedLocalModelAllocationValidity",
 "GovernedLocalModelResourceAllocation", "GovernedLocalModelResourceAllocator", "GovernedLocalModelResourceBounds",
 "GovernedLocalModelResourceConsumptionReceipt", "GovernedLocalModelResourceError", "GovernedLocalModelResourceLedger",
 "GovernedLocalModelResourceLedgerObservation",
 "GovernedLocalModelResourcePolicy"]
