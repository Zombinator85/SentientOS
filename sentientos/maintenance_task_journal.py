"""Canonical append-only maintenance-task journal.

This module records and replays repository-maintenance task state only. It does
not invoke providers, network, subprocesses, Git, host actuators, or runtime
capability adoption. The only intended effect is writing journal/snapshot files
inside an explicit external state root supplied by the caller.
"""

from __future__ import annotations

import argparse
import dataclasses
import fcntl
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

EVENT_SCHEMA = "sentientos.maintenance_task_event:v1"
SNAPSHOT_SCHEMA = "sentientos.maintenance_task_snapshot:v1"
ZERO_DIGEST = "sha256:" + "0" * 64

EVENT_TYPES = frozenset({
    "task_created",
    "authority_lease_bound",
    "authority_lease_revoked",
    "attempt_started",
    "attempt_heartbeat",
    "agent_session_bound",
    "implementation_completed",
    "implementation_failed",
    "implementation_interrupted",
    "validation_started",
    "validation_passed",
    "validation_failed",
    "ready_to_commit_recorded",
    "commit_recorded",
    "publication_started",
    "publication_succeeded",
    "publication_failed",
    "recovery_started",
    "recovery_completed",
    "task_blocked",
    "task_cancelled",
    "task_closed",
})

APPEND_STATUSES = frozenset({
    "event_appended",
    "event_already_recorded",
    "event_conflict",
    "transition_rejected",
    "journal_integrity_failed",
})

INTEGRITY_STATUSES = frozenset({
    "journal_ready",
    "journal_tail_incomplete",
    "journal_chain_broken",
    "journal_record_invalid",
    "journal_sequence_invalid",
    "journal_digest_mismatch",
})

REJECTION_REASONS = frozenset({
    "unknown_event_type",
    "task_not_created",
    "task_already_created",
    "task_terminal",
    "missing_authority_lease",
    "authority_lease_already_active",
    "authority_lease_not_active",
    "authority_lease_scope_expanded",
    "attempt_already_active",
    "attempt_not_active",
    "attempt_id_reused",
    "attempt_terminal",
    "validation_before_successful_implementation",
    "validation_cycle_already_active",
    "validation_reference_reused",
    "validation_reference_mismatch",
    "validation_attempt_mismatch",
    "validation_cycle_not_active",
    "validation_cycle_already_terminal",
    "attempt_after_validation_passed",
    "corrective_parent_validation_required",
    "corrective_retry_ordinal_invalid",
    "corrective_retry_limit_exceeded",
    "commit_readiness_validation_mismatch",
    "commit_readiness_attempt_mismatch",
    "commit_ready_before_validation_passed",
    "commit_before_ready",
    "publication_before_commit",
    "publication_not_started",
    "close_with_active_attempt",
    "duplicate_event_conflict",
    "journal_not_ready",
})

TERMINAL_TASK_STATES = frozenset({"closed", "cancelled"})
TERMINAL_ATTEMPT_EVENTS = frozenset({"implementation_completed", "implementation_failed", "implementation_interrupted"})


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _identity(prefix: str, payload: Mapping[str, Any]) -> str:
    return prefix + "_" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()[:32]


def normalize_objective(text: str) -> str:
    return " ".join(text.strip().split())


def derive_task_id(*, candidate_ref: str, base_sha: str, objective: str | None = None, contract_digest: str | None = None, admitted_scope_digest: str) -> str:
    if not objective and not contract_digest:
        raise ValueError("objective_or_contract_digest_required")
    return _identity("mtask", {"candidate_ref": candidate_ref, "base_sha": base_sha, "objective": normalize_objective(objective or ""), "contract_digest": contract_digest or "", "admitted_scope_digest": admitted_scope_digest})


def derive_attempt_id(task_id: str, attempt_ordinal: int) -> str:
    return _identity("mattempt", {"task_id": task_id, "attempt_ordinal": attempt_ordinal})


def derive_authority_lease_id(task_id: str, scope_digest: str, lease_ordinal: int = 1) -> str:
    return _identity("mlease", {"task_id": task_id, "scope_digest": scope_digest, "lease_ordinal": lease_ordinal})


def derive_agent_session_ref_id(task_id: str, attempt_id: str, opaque_ref: str) -> str:
    return _identity("magent", {"task_id": task_id, "attempt_id": attempt_id, "opaque_ref": opaque_ref})


def derive_validation_ref_id(task_id: str, attempt_id: str, validation_digest: str) -> str:
    return _identity("mvalidation", {"task_id": task_id, "attempt_id": attempt_id, "validation_digest": validation_digest})


def derive_commit_ref_id(task_id: str, commit_sha: str) -> str:
    return _identity("mcommit", {"task_id": task_id, "commit_sha": commit_sha})


def derive_publication_ref_id(task_id: str, target_ref: str) -> str:
    return _identity("mpub", {"task_id": task_id, "target_ref": target_ref})


@dataclass(frozen=True)
class MaintenanceTaskEvent:
    event_id: str
    task_id: str
    sequence: int
    event_type: str
    previous_event_digest: str
    payload: Mapping[str, Any]
    recorded_at: str
    writer: str
    repository_sha: str | None = None
    schema_version: str = EVENT_SCHEMA
    event_digest: str = ""

    def digest_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "task_id": self.task_id,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "previous_event_digest": self.previous_event_digest,
            "payload": self.payload,
            "recorded_at": self.recorded_at,
            "writer": self.writer,
            "repository_sha": self.repository_sha,
        }

    def with_digest(self) -> "MaintenanceTaskEvent":
        return dataclasses.replace(self, event_digest=sha256_digest(self.digest_payload()))

    def to_dict(self) -> dict[str, Any]:
        value = self.digest_payload()
        value["event_digest"] = self.event_digest
        return value

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MaintenanceTaskEvent":
        required = {"schema_version", "event_id", "task_id", "sequence", "event_type", "previous_event_digest", "payload", "recorded_at", "writer", "event_digest"}
        if set(value) - (required | {"repository_sha"}) or not required.issubset(value):
            raise ValueError("journal_record_invalid")
        if value["schema_version"] != EVENT_SCHEMA or not isinstance(value["payload"], Mapping):
            raise ValueError("journal_record_invalid")
        event = cls(
            event_id=str(value["event_id"]),
            task_id=str(value["task_id"]),
            sequence=int(value["sequence"]),
            event_type=str(value["event_type"]),
            previous_event_digest=str(value["previous_event_digest"]),
            payload=dict(value["payload"]),
            recorded_at=str(value["recorded_at"]),
            writer=str(value["writer"]),
            repository_sha=None if value.get("repository_sha") is None else str(value.get("repository_sha")),
            event_digest=str(value["event_digest"]),
        )
        return event


def build_event(*, event_id: str, task_id: str, sequence: int, event_type: str, previous_event_digest: str, payload: Mapping[str, Any], recorded_at: str | None = None, writer: str = "maintenance_task_journal", repository_sha: str | None = None) -> MaintenanceTaskEvent:
    if event_type not in EVENT_TYPES:
        raise ValueError("unknown_event_type")
    event = MaintenanceTaskEvent(event_id=event_id, task_id=task_id, sequence=sequence, event_type=event_type, previous_event_digest=previous_event_digest, payload=dict(payload), recorded_at=recorded_at or datetime.now(timezone.utc).isoformat(), writer=writer, repository_sha=repository_sha)
    return event.with_digest()


@dataclass(frozen=True)
class ReplayResult:
    events: tuple[MaintenanceTaskEvent, ...]
    integrity_status: str
    reason_code: str | None = None
    last_valid_sequence: int = 0
    last_event_digest: str = ZERO_DIGEST


@dataclass(frozen=True)
class AppendResult:
    status: str
    reason_code: str | None
    event: MaintenanceTaskEvent | None
    snapshot: Mapping[str, Any]


@dataclass
class _State:
    task_id: str | None = None
    candidate_ref: str | None = None
    base_sha: str | None = None
    candidate_revision_digest: str | None = None
    canonical_candidate_digest: str | None = None
    selection_digest: str | None = None
    selector_policy_digest: str | None = None
    admitted_scope_digest: str | None = None
    operator_grant_id: str | None = None
    operator_grant_digest: str | None = None
    maximum_attempts: int | None = None
    maximum_corrective_retries: int | None = None
    lifecycle_state: str = "not_created"
    active_authority_lease: dict[str, Any] | None = None
    authority_leases: dict[str, dict[str, Any]] = field(default_factory=dict)
    active_attempt: dict[str, Any] | None = None
    completed_attempts: list[dict[str, Any]] = field(default_factory=list)
    used_attempt_ids: set[str] = field(default_factory=set)
    agent_session_refs: list[dict[str, Any]] = field(default_factory=list)
    latest_heartbeat: dict[str, Any] | None = None
    implementation_result: dict[str, Any] | None = None
    validation_state: str = "not_started"
    validation_result: dict[str, Any] | None = None
    validation_cycles: list[dict[str, Any]] = field(default_factory=list)
    active_validation_cycle: dict[str, Any] | None = None
    used_validation_refs: set[str] = field(default_factory=set)
    commit_readiness: dict[str, Any] | None = None
    commit_reference: dict[str, Any] | None = None
    publication_state: str = "not_started"
    publication_reference: dict[str, Any] | None = None
    recovery_state: str = "not_started"
    blockers: list[dict[str, Any]] = field(default_factory=list)


def _scope(value: Mapping[str, Any]) -> str:
    return str(value.get("scope_digest") or value.get("admitted_scope_digest") or "")


def apply_event(state: _State, event: MaintenanceTaskEvent, *, evaluation_time: str | None = None) -> str | None:
    if event.event_type not in EVENT_TYPES:
        return "unknown_event_type"
    if state.lifecycle_state in TERMINAL_TASK_STATES and event.event_type not in {"task_closed", "task_cancelled"}:
        return "task_terminal"
    p = dict(event.payload)
    if event.event_type == "task_created":
        if state.task_id is not None:
            return "task_already_created"
        state.task_id = event.task_id
        state.candidate_ref = str(p.get("candidate_ref") or p.get("candidate_id") or "")
        state.base_sha = str(p.get("base_sha") or event.repository_sha or "")
        state.candidate_revision_digest = p.get("candidate_revision_digest")
        state.canonical_candidate_digest = p.get("canonical_candidate_digest")
        state.selection_digest = p.get("selection_digest")
        state.selector_policy_digest = p.get("selector_policy_digest")
        state.admitted_scope_digest = p.get("admitted_scope_digest")
        state.operator_grant_id = p.get("operator_grant_id")
        state.operator_grant_digest = p.get("operator_grant_digest")
        state.maximum_attempts = int(p["maximum_attempts"]) if p.get("maximum_attempts") is not None else None
        state.maximum_corrective_retries = int(p["maximum_corrective_retries"]) if p.get("maximum_corrective_retries") is not None else None
        state.lifecycle_state = "created"
        return None
    if state.task_id is None:
        return "task_not_created"
    if event.event_type == "authority_lease_bound":
        lease_id = str(p.get("lease_id", ""))
        if state.active_authority_lease is not None:
            return "authority_lease_already_active"
        if state.authority_leases:
            first_scope = next(iter(state.authority_leases.values())).get("scope_digest")
            if first_scope and _scope(p) and _scope(p) != first_scope:
                return "authority_lease_scope_expanded"
        bind = {"candidate_revision_digest": p.get("candidate_revision_digest"), "canonical_candidate_digest": p.get("canonical_candidate_digest"), "selection_digest": p.get("selection_digest"), "selector_policy_digest": p.get("selector_policy_digest"), "admitted_scope_digest": _scope(p), "operator_grant_id": p.get("operator_grant_id"), "operator_grant_digest": p.get("operator_grant_digest")}
        for k, v in bind.items():
            if v is not None and getattr(state, k if k != "admitted_scope_digest" else "admitted_scope_digest") not in {None, v}:
                return "authority_lease_scope_expanded"
            if v is not None and hasattr(state, k):
                setattr(state, k, v)
        state.maximum_attempts = int(p["maximum_attempts"]) if p.get("maximum_attempts") is not None else state.maximum_attempts
        state.maximum_corrective_retries = int(p["maximum_corrective_retries"]) if p.get("maximum_corrective_retries") is not None else state.maximum_corrective_retries
        lease = {"lease_id": lease_id, "lease_digest": p.get("lease_digest"), "scope_digest": _scope(p), "expires_at": p.get("expires_at"), "revoked": False, "payload": p}
        state.authority_leases[lease_id] = lease
        state.active_authority_lease = lease
        state.lifecycle_state = "lease_bound"
        return None
    if event.event_type == "authority_lease_revoked":
        if state.active_authority_lease is None:
            return "authority_lease_not_active"
        state.active_authority_lease["revoked"] = True
        state.active_authority_lease = None
        state.lifecycle_state = "lease_revoked"
        return None
    if event.event_type == "attempt_started":
        if state.validation_state == "passed":
            return "attempt_after_validation_passed"
        parent_ref = p.get("parent_validation_ref_id")
        retry_ord = int(p.get("corrective_retry_ordinal", 0) or 0)
        if state.validation_state == "failed" or retry_ord:
            if not parent_ref or not state.validation_result or parent_ref != state.validation_result["payload"].get("validation_ref_id"):
                return "corrective_parent_validation_required"
            expected_retry = max([int(a.get("payload", {}).get("corrective_retry_ordinal", 0) or 0) for a in state.completed_attempts] + [0]) + 1
            if retry_ord != expected_retry:
                return "corrective_retry_ordinal_invalid"
            if state.maximum_corrective_retries is not None and retry_ord > state.maximum_corrective_retries:
                return "corrective_retry_limit_exceeded"
            if _scope(p) and _scope(p) != state.admitted_scope_digest:
                return "authority_lease_scope_expanded"
        if state.active_authority_lease is None:
            return "missing_authority_lease"
        attempt_id = str(p.get("attempt_id", ""))
        if state.active_attempt is not None:
            return "attempt_already_active"
        if attempt_id in state.used_attempt_ids:
            return "attempt_id_reused"
        if state.active_authority_lease.get("lease_digest") and str(p.get("lease_id") or "") != state.active_authority_lease.get("lease_id"):
            return "authority_lease_not_active"
        if _scope(p) and _scope(p) != state.active_authority_lease.get("scope_digest"):
            return "authority_lease_scope_expanded"
        if state.maximum_attempts is not None and len(state.used_attempt_ids) >= state.maximum_attempts:
            return "attempt_id_reused"
        state.used_attempt_ids.add(attempt_id)
        state.active_attempt = {"attempt_id": attempt_id, "status": "active", "started_at": event.recorded_at, "payload": p}
        state.commit_readiness = None
        state.lifecycle_state = "attempt_active"
        return None
    if event.event_type == "attempt_heartbeat":
        if state.active_attempt is None:
            return "attempt_not_active"
        state.latest_heartbeat = {"attempt_id": state.active_attempt["attempt_id"], "recorded_at": event.recorded_at, "payload": p}
        return None
    if event.event_type == "agent_session_bound":
        if state.active_attempt is None:
            return "attempt_not_active"
        state.agent_session_refs.append({"attempt_id": state.active_attempt["attempt_id"], "payload": p})
        return None
    if event.event_type in TERMINAL_ATTEMPT_EVENTS:
        if state.active_attempt is None:
            return "attempt_not_active"
        result_state = event.event_type.removeprefix("implementation_")
        done = dict(state.active_attempt)
        done["status"] = result_state
        done["completed_at"] = event.recorded_at
        done["result"] = p
        state.completed_attempts.append(done)
        state.active_attempt = None
        state.implementation_result = {"status": result_state, "payload": p, "recorded_at": event.recorded_at}
        state.lifecycle_state = "implementation_" + result_state
        return None
    if event.event_type == "validation_started":
        if not state.implementation_result or state.implementation_result["status"] != "completed":
            return "validation_before_successful_implementation"
        ref = str(p.get("validation_ref_id") or "")
        if state.active_validation_cycle is not None:
            return "validation_cycle_already_active"
        if ref in state.used_validation_refs:
            return "validation_reference_reused"
        latest_attempt = state.completed_attempts[-1]["attempt_id"] if state.completed_attempts else None
        if p.get("attempt_id") and p.get("attempt_id") != latest_attempt:
            return "validation_attempt_mismatch"
        cycle = {"validation_ref_id": ref, "attempt_id": latest_attempt, "session_id": p.get("session_id"), "plan_digest": p.get("plan_digest"), "change_manifest_digest": p.get("change_manifest_digest"), "worktree_descriptor_digest": p.get("worktree_descriptor_digest"), "status": "started", "started_at": event.recorded_at, "payload": p}
        state.used_validation_refs.add(ref)
        state.active_validation_cycle = cycle
        state.validation_cycles.append(cycle)
        state.validation_state = "started"
        return None
    if event.event_type in {"validation_passed", "validation_failed"}:
        if not state.implementation_result or state.implementation_result["status"] != "completed":
            return "validation_before_successful_implementation"
        if state.active_validation_cycle is None:
            return "validation_cycle_not_active"
        ref = str(p.get("validation_ref_id") or "")
        if ref != state.active_validation_cycle.get("validation_ref_id"):
            return "validation_reference_mismatch"
        if p.get("attempt_id") and p.get("attempt_id") != state.active_validation_cycle.get("attempt_id"):
            return "validation_attempt_mismatch"
        status = "passed" if event.event_type == "validation_passed" else "failed"
        state.active_validation_cycle.update({"status": status, "completed_at": event.recorded_at, "result_digest": p.get("result_digest"), "terminal_payload": p})
        state.active_validation_cycle = None
        state.validation_state = status
        state.validation_result = {"status": status, "payload": p, "recorded_at": event.recorded_at}
        state.lifecycle_state = "validation_" + status
        return None
    if event.event_type == "ready_to_commit_recorded":
        if state.validation_state != "passed" or not state.validation_result:
            return "commit_ready_before_validation_passed"
        if p.get("validation_ref_id") and p.get("validation_ref_id") != state.validation_result["payload"].get("validation_ref_id"):
            return "commit_readiness_validation_mismatch"
        latest_attempt = state.completed_attempts[-1]["attempt_id"] if state.completed_attempts else None
        if p.get("attempt_id") and p.get("attempt_id") != latest_attempt:
            return "commit_readiness_attempt_mismatch"
        state.commit_readiness = {"payload": p, "recorded_at": event.recorded_at}
        state.lifecycle_state = "ready_to_commit"
        return None
    if event.event_type == "commit_recorded":
        if state.commit_readiness is None:
            return "commit_before_ready"
        state.commit_reference = {"payload": p, "recorded_at": event.recorded_at}
        state.lifecycle_state = "commit_recorded"
        return None
    if event.event_type == "publication_started":
        if state.commit_reference is None:
            return "publication_before_commit"
        state.publication_state = "started"
        state.publication_reference = {"payload": p, "recorded_at": event.recorded_at}
        return None
    if event.event_type == "publication_failed":
        if state.publication_state == "not_started":
            return "publication_not_started"
        state.publication_state = "failed"
        state.publication_reference = {"payload": p, "recorded_at": event.recorded_at}
        state.lifecycle_state = "publication_failed"
        return None
    if event.event_type == "publication_succeeded":
        if state.commit_reference is None:
            return "publication_before_commit"
        state.publication_state = "succeeded"
        state.publication_reference = {"payload": p, "recorded_at": event.recorded_at}
        state.lifecycle_state = "publication_succeeded"
        return None
    if event.event_type == "recovery_started":
        state.recovery_state = "started"
        state.lifecycle_state = "recovery_started"
        return None
    if event.event_type == "recovery_completed":
        state.recovery_state = "completed"
        state.lifecycle_state = "recovery_completed"
        return None
    if event.event_type == "task_blocked":
        state.blockers.append({"payload": p, "recorded_at": event.recorded_at})
        state.lifecycle_state = "blocked"
        return None
    if event.event_type == "task_cancelled":
        if state.active_attempt is not None:
            return "close_with_active_attempt"
        state.lifecycle_state = "cancelled"
        return None
    if event.event_type == "task_closed":
        if state.active_attempt is not None:
            return "close_with_active_attempt"
        state.lifecycle_state = "closed"
        return None
    return "unknown_event_type"


def _lease_status(lease: Mapping[str, Any] | None, evaluation_time: str | None) -> str:
    if lease is None:
        return "none"
    if lease.get("revoked"):
        return "revoked"
    exp = lease.get("expires_at")
    if exp and evaluation_time and str(exp) <= evaluation_time:
        return "expired"
    return "active"


def reduce_events(events: Sequence[MaintenanceTaskEvent], *, evaluation_time: str | None = None, integrity_status: str = "journal_ready", reason_code: str | None = None, last_valid_sequence: int | None = None, last_event_digest: str | None = None) -> dict[str, Any]:
    state = _State()
    transition_reason: str | None = None
    applied = 0
    for event in events:
        reason = apply_event(state, event, evaluation_time=evaluation_time)
        if reason:
            transition_reason = reason
            integrity_status = "journal_record_invalid"
            break
        applied += 1
    snapshot: dict[str, Any] = {
        "schema_version": SNAPSHOT_SCHEMA,
        "task_id": state.task_id,
        "candidate_ref": state.candidate_ref,
        "base_sha": state.base_sha,
        "candidate_revision_digest": state.candidate_revision_digest,
        "canonical_candidate_digest": state.canonical_candidate_digest,
        "selection_digest": state.selection_digest,
        "selector_policy_digest": state.selector_policy_digest,
        "admitted_scope_digest": state.admitted_scope_digest,
        "operator_grant_id": state.operator_grant_id,
        "operator_grant_digest": state.operator_grant_digest,
        "active_lease_id": state.active_authority_lease.get("lease_id") if state.active_authority_lease else None,
        "active_lease_digest": state.active_authority_lease.get("lease_digest") if state.active_authority_lease else None,
        "lease_expiry": state.active_authority_lease.get("expires_at") if state.active_authority_lease else None,
        "maximum_attempts": state.maximum_attempts,
        "maximum_corrective_retries": state.maximum_corrective_retries,
        "lifecycle_state": state.lifecycle_state,
        "terminal": state.lifecycle_state in TERMINAL_TASK_STATES,
        "active_authority_lease": state.active_authority_lease,
        "lease_status": _lease_status(state.active_authority_lease, evaluation_time),
        "lease_expiry_evaluation_time": evaluation_time,
        "active_attempt": state.active_attempt,
        "completed_attempts": state.completed_attempts,
        "agent_session_refs": state.agent_session_refs,
        "latest_heartbeat": state.latest_heartbeat,
        "implementation_result": state.implementation_result,
        "validation_result": state.validation_result,
        "validation_cycles": state.validation_cycles,
        "active_validation_cycle": state.active_validation_cycle,
        "validation_state": state.validation_state,
        "commit_readiness": state.commit_readiness,
        "commit_reference": state.commit_reference,
        "publication_state": state.publication_state,
        "publication_reference": state.publication_reference,
        "recovery_state": state.recovery_state,
        "blockers": state.blockers,
        "last_valid_sequence": last_valid_sequence if last_valid_sequence is not None else applied,
        "last_event_digest": last_event_digest if last_event_digest is not None else (events[applied - 1].event_digest if applied else ZERO_DIGEST),
        "journal_integrity_status": integrity_status,
        "reason_code": transition_reason or reason_code,
    }
    snapshot["snapshot_digest"] = sha256_digest(snapshot)
    return snapshot


def _validate_chain(events: list[MaintenanceTaskEvent]) -> ReplayResult:
    prev = ZERO_DIGEST
    seen: dict[str, bytes] = {}
    valid: list[MaintenanceTaskEvent] = []
    for index, event in enumerate(events, start=1):
        actual = event.with_digest().event_digest
        if event.event_digest != actual:
            return ReplayResult(tuple(valid), "journal_digest_mismatch", "journal_digest_mismatch", index - 1, prev)
        if event.sequence != index:
            return ReplayResult(tuple(valid), "journal_sequence_invalid", "journal_sequence_invalid", index - 1, prev)
        if event.previous_event_digest != prev:
            return ReplayResult(tuple(valid), "journal_chain_broken", "journal_chain_broken", index - 1, prev)
        raw = event.canonical_bytes()
        if event.event_id in seen and seen[event.event_id] != raw:
            return ReplayResult(tuple(valid), "journal_record_invalid", "duplicate_event_conflict", index - 1, prev)
        seen[event.event_id] = raw
        valid.append(event)
        prev = event.event_digest
    return ReplayResult(tuple(valid), "journal_ready", None, len(valid), prev)


def replay_journal(journal_path: Path) -> ReplayResult:
    if not journal_path.exists():
        return ReplayResult((), "journal_ready", None, 0, ZERO_DIGEST)
    data = journal_path.read_bytes()
    has_partial_tail = bool(data) and not data.endswith(b"\n")
    rows = data.splitlines()
    parse_rows = rows[:-1] if has_partial_tail else rows
    events: list[MaintenanceTaskEvent] = []
    for raw in parse_rows:
        try:
            value = json.loads(raw.decode("utf-8"))
            events.append(MaintenanceTaskEvent.from_dict(value))
        except Exception:
            return ReplayResult(tuple(events), "journal_record_invalid", "journal_record_invalid", len(events), events[-1].event_digest if events else ZERO_DIGEST)
    checked = _validate_chain(events)
    if checked.integrity_status != "journal_ready":
        return checked
    if has_partial_tail:
        return ReplayResult(checked.events, "journal_tail_incomplete", "journal_tail_incomplete", checked.last_valid_sequence, checked.last_event_digest)
    return checked


def resolve_state_root(state_root: str | Path, *, repo_root: str | Path | None = None) -> Path:
    root = Path(state_root)
    if not root.exists() or not root.is_dir():
        raise ValueError("state_root_not_directory")
    resolved = root.resolve(strict=True)
    repo = Path(repo_root or Path.cwd()).resolve(strict=True)
    git = (repo / ".git").resolve(strict=False)
    if resolved == repo or repo in resolved.parents or resolved == git or git in resolved.parents:
        raise ValueError("state_root_inside_repository_rejected")
    return resolved


def journal_path_for(state_root: str | Path, task_id: str, *, repo_root: str | Path | None = None) -> Path:
    root = resolve_state_root(state_root, repo_root=repo_root)
    return root / "maintenance_tasks" / f"{task_id}.jsonl"


def _lock_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".lock")


def append_event(state_root: str | Path, event_type: str, *, task_id: str, payload: Mapping[str, Any], event_id: str | None = None, writer: str = "maintenance_task_journal", repository_sha: str | None = None, recorded_at: str | None = None, repo_root: str | Path | None = None, evaluation_time: str | None = None) -> AppendResult:
    if event_type not in EVENT_TYPES:
        return AppendResult("transition_rejected", "unknown_event_type", None, {})
    path = journal_path_for(state_root, task_id, repo_root=repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _lock_path(path)
    lock.touch(exist_ok=True)
    before_stat = path.lstat() if path.exists() else None
    if path.exists() and path.is_symlink():
        return AppendResult("journal_integrity_failed", "state_file_symlink_rejected", None, {})
    with lock.open("r+") as lock_fh:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        if path.exists() and path.is_symlink():
            return AppendResult("journal_integrity_failed", "state_file_symlink_rejected", None, {})
        if before_stat and path.exists():
            after_stat = path.lstat()
            if (before_stat.st_dev, before_stat.st_ino, before_stat.st_mode) != (after_stat.st_dev, after_stat.st_ino, after_stat.st_mode):
                return AppendResult("journal_integrity_failed", "state_file_identity_changed", None, {})
        replay = replay_journal(path)
        snapshot = reduce_events(replay.events, evaluation_time=evaluation_time, integrity_status=replay.integrity_status, reason_code=replay.reason_code, last_valid_sequence=replay.last_valid_sequence, last_event_digest=replay.last_event_digest)
        if replay.integrity_status not in {"journal_ready"}:
            return AppendResult("journal_integrity_failed", replay.integrity_status, None, snapshot)
        next_seq = replay.last_valid_sequence + 1
        prev = replay.last_event_digest
        eid = event_id or _identity("mevent", {"task_id": task_id, "sequence": next_seq, "event_type": event_type, "payload": payload})
        new_event = build_event(event_id=eid, task_id=task_id, sequence=next_seq, event_type=event_type, previous_event_digest=prev, payload=payload, recorded_at=recorded_at, writer=writer, repository_sha=repository_sha)
        for existing in replay.events:
            if existing.event_id == eid:
                same_semantic_event = (
                    existing.task_id == task_id
                    and existing.event_type == event_type
                    and dict(existing.payload) == dict(payload)
                    and existing.repository_sha == repository_sha
                    and (recorded_at is None or existing.recorded_at == recorded_at)
                    and existing.writer == writer
                )
                if existing.canonical_bytes() == new_event.canonical_bytes() or same_semantic_event:
                    return AppendResult("event_already_recorded", None, existing, snapshot)
                return AppendResult("event_conflict", "duplicate_event_conflict", None, snapshot)
        trial = list(replay.events) + [new_event]
        trial_snapshot = reduce_events(trial, evaluation_time=evaluation_time)
        if trial_snapshot.get("reason_code"):
            return AppendResult("transition_rejected", str(trial_snapshot["reason_code"]), None, snapshot)
        with path.open("ab") as fh:
            fh.write(new_event.canonical_bytes() + b"\n")
            fh.flush()
            os.fsync(fh.fileno())
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        return AppendResult("event_appended", None, new_event, trial_snapshot)



def discover_maintenance_task_snapshots(state_root: str | Path, candidate_ref: str | None = None, *, repo_root: str | Path | None = None, evaluation_time: str | None = None) -> tuple[dict[str, Any], ...]:
    root = resolve_state_root(state_root, repo_root=repo_root)
    task_dir = root / "maintenance_tasks"
    if not task_dir.exists():
        return ()
    snapshots: list[dict[str, Any]] = []
    for path in sorted(task_dir.glob("*.jsonl"), key=lambda x: x.name):
        if path.is_symlink():
            snapshots.append({"task_id": path.stem, "candidate_ref": None, "lifecycle_state": "unknown", "lease_state": "unknown", "integrity_status": "journal_symlink_rejected"})
            continue
        replay = replay_journal(path)
        snap = reduce_events(replay.events, evaluation_time=evaluation_time, integrity_status=replay.integrity_status, reason_code=replay.reason_code, last_valid_sequence=replay.last_valid_sequence, last_event_digest=replay.last_event_digest)
        if candidate_ref is None or snap.get("candidate_ref") == candidate_ref or (snap.get("candidate_ref") is None and snap.get("journal_integrity_status") != "journal_ready"):
            snapshots.append({"task_id": path.stem, "candidate_ref": snap.get("candidate_ref"), "candidate_revision_digest": snap.get("candidate_revision_digest"), "lifecycle_state": snap.get("lifecycle_state"), "lease_state": snap.get("lease_status"), "integrity_status": snap.get("journal_integrity_status"), "snapshot": snap})
    return tuple(snapshots)

def materialize_snapshot(state_root: str | Path, task_id: str, output_path: str | Path | None = None, *, repo_root: str | Path | None = None, evaluation_time: str | None = None) -> dict[str, Any]:
    path = journal_path_for(state_root, task_id, repo_root=repo_root)
    replay = replay_journal(path)
    snapshot = reduce_events(replay.events, evaluation_time=evaluation_time, integrity_status=replay.integrity_status, reason_code=replay.reason_code, last_valid_sequence=replay.last_valid_sequence, last_event_digest=replay.last_event_digest)
    if output_path is not None:
        out = Path(output_path)
        root = resolve_state_root(state_root, repo_root=repo_root)
        out_resolved_parent = out.parent.resolve(strict=True)
        if root != out_resolved_parent and root not in out_resolved_parent.parents:
            raise ValueError("snapshot_output_outside_state_root")
        data = canonical_json_bytes(snapshot) + b"\n"
        with tempfile.NamedTemporaryFile(dir=out.parent, delete=False) as tmp:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_name = tmp.name
        os.replace(tmp_name, out)
    return snapshot


def cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="maintenance task journal")
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--repo-root", default=str(Path.cwd()))
    sub = parser.add_subparsers(dest="cmd", required=True)
    ap = sub.add_parser("append")
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--event-type", required=True)
    ap.add_argument("--payload-json")
    ap.add_argument("--payload-file")
    ap.add_argument("--event-id")
    ap.add_argument("--recorded-at")
    ap.add_argument("--writer", default="maintenance_task_journal_cli")
    ap.add_argument("--repository-sha")
    for name in ("inspect", "verify", "materialize"):
        sp = sub.add_parser(name)
        sp.add_argument("--task-id", required=True)
        if name == "materialize":
            sp.add_argument("--output", required=True)
    ns = parser.parse_args(argv)
    try:
        if ns.cmd == "append":
            if ns.payload_file:
                payload = json.loads(Path(ns.payload_file).read_text(encoding="utf-8"))
            elif ns.payload_json:
                if len(ns.payload_json) > 65536:
                    raise ValueError("payload_json_too_large")
                payload = json.loads(ns.payload_json)
            else:
                payload = {}
            result = append_event(ns.state_root, ns.event_type, task_id=ns.task_id, payload=payload, event_id=ns.event_id, writer=ns.writer, repository_sha=ns.repository_sha, recorded_at=ns.recorded_at, repo_root=ns.repo_root)
            print(canonical_json_bytes({"status": result.status, "reason_code": result.reason_code, "event": result.event.to_dict() if result.event else None, "snapshot": result.snapshot}).decode("utf-8"))
            return 0 if result.status in {"event_appended", "event_already_recorded"} else 2
        if ns.cmd == "inspect":
            replay = replay_journal(journal_path_for(ns.state_root, ns.task_id, repo_root=ns.repo_root))
            print(canonical_json_bytes({"events": [e.to_dict() for e in replay.events], "integrity_status": replay.integrity_status, "reason_code": replay.reason_code, "last_valid_sequence": replay.last_valid_sequence, "last_event_digest": replay.last_event_digest}).decode("utf-8"))
            return 0 if replay.integrity_status in {"journal_ready", "journal_tail_incomplete"} else 2
        if ns.cmd == "verify":
            replay = replay_journal(journal_path_for(ns.state_root, ns.task_id, repo_root=ns.repo_root))
            print(canonical_json_bytes({"integrity_status": replay.integrity_status, "reason_code": replay.reason_code, "last_valid_sequence": replay.last_valid_sequence, "last_event_digest": replay.last_event_digest}).decode("utf-8"))
            return 0 if replay.integrity_status == "journal_ready" else 2
        snapshot = materialize_snapshot(ns.state_root, ns.task_id, ns.output, repo_root=ns.repo_root)
        print(canonical_json_bytes(snapshot).decode("utf-8"))
        return 0 if snapshot["journal_integrity_status"] == "journal_ready" else 2
    except Exception as exc:
        print(canonical_json_bytes({"status": "error", "reason_code": str(exc)}).decode("utf-8"))
        return 2


__all__ = [
    "APPEND_STATUSES", "EVENT_SCHEMA", "EVENT_TYPES", "INTEGRITY_STATUSES", "REJECTION_REASONS", "SNAPSHOT_SCHEMA", "AppendResult", "MaintenanceTaskEvent", "ReplayResult", "append_event", "build_event", "canonical_json_bytes", "derive_agent_session_ref_id", "derive_attempt_id", "derive_authority_lease_id", "derive_commit_ref_id", "derive_publication_ref_id", "derive_task_id", "derive_validation_ref_id", "discover_maintenance_task_snapshots", "journal_path_for", "materialize_snapshot", "reduce_events", "replay_journal", "resolve_state_root", "sha256_digest", "cli",
]
