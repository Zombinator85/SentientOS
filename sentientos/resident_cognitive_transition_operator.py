"""Installation-custodied operator ingress for one resident transition stage.

The mailbox is a request transport, never an authority source.  The transition
controller remains responsible for verifying the exact stage approval and all
subordinate owners retain their independent admissions.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from .resident_cognitive_model_transition_experiment import (
    PHASES, TransitionError, TransitionProtocol, TransitionStageExecutionContext, digest,
)
from .windows_handle_custody import WindowsHandleCustodyError, read_explicit_file, read_regular_files

CONFIG_SCHEMA = "sentientos.resident_cognitive_transition_live_config:v1"
REQUEST_SCHEMA = "sentientos.resident_cognitive_transition_operator_request:v1"
RECEIPT_SCHEMA = "sentientos.resident_cognitive_transition_operator_request_receipt:v1"
REQUEST_CUSTODY = "state/resident-cognitive-transition/operator-requests"
RECEIPT_CUSTODY = "state/resident-cognitive-transition/operator-request-receipts.jsonl"
JOURNAL_CUSTODY = "state/resident-cognitive-transition/transition.journal.jsonl"
PROTOCOL_CUSTODY = "state/resident-cognitive-transition/protocol.json"
MAX_TRANSITION_RECEIPTS = 4096
MAX_TRANSITION_RECEIPT_BYTES = 16_777_216
MAX_TRANSITION_REQUESTS = 4096
MAX_TRANSITION_REQUEST_BYTES = 262_144
MAX_TRANSITION_REQUEST_ROOT_BYTES = 67_108_864


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(_plain(value), sort_keys=True, separators=(",", ":")) + "\n").encode()


def _time(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise TransitionError("operator_request_validity_invalid") from exc
    if parsed.tzinfo is None:
        raise TransitionError("operator_request_validity_invalid")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class LiveTransitionConfig:
    enabled: bool
    installation_identity: str
    protocol_id: str
    protocol_digest: str
    request_custody: str
    journal_custody: str
    journal_identity: str

    @classmethod
    def load(cls, path: Path) -> "LiveTransitionConfig":
        try:
            raw = read_explicit_file(Path(path), max_bytes=65_536)
            value = json.loads(raw.decode("utf-8"))
        except (WindowsHandleCustodyError, UnicodeError, json.JSONDecodeError) as exc:
            raise TransitionError("live_transition_config_unavailable") from exc
        required = {"schema_version", "enabled", "installation_identity", "protocol_id",
                    "protocol_digest", "request_custody", "journal_custody", "journal_identity"}
        if not isinstance(value, dict) or set(value) != required or value.get("schema_version") != CONFIG_SCHEMA:
            raise TransitionError("live_transition_config_invalid")
        config = cls(**{key: value[key] for key in required - {"schema_version"}})
        if (not isinstance(config.enabled, bool) or not config.installation_identity
                or config.request_custody != REQUEST_CUSTODY or config.journal_custody != JOURNAL_CUSTODY
                or not config.journal_identity or config.protocol_id in {"latest", "current", "*"}
                or len(config.protocol_digest) != 64):
            raise TransitionError("live_transition_config_invalid")
        return config


def build_request(*, installation_identity: str, protocol: Mapping[str, Any], requested_stage: str,
                  expected_prior_phase: str, expected_journal_head: str,
                  stage_approval: Mapping[str, Any], subordinate_approvals: Sequence[Mapping[str, Any]],
                  operation_id: str, correlation_id: str, operator_identity: str,
                  operator_provenance: Mapping[str, Any], created_at: str, expires_at: str,
                  stage_evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build a non-authoritative packet from already-issued approval artifacts."""
    if requested_stage not in PHASES or not operation_id or not correlation_id or not operator_identity:
        raise TransitionError("operator_request_invalid")
    stage = _plain(stage_approval)
    subordinate = [_plain(item) for item in subordinate_approvals]
    approval_digest = str(stage.get("approval_digest", ""))
    if not approval_digest or digest({k: v for k, v in stage.items() if k != "approval_digest"}) != approval_digest:
        raise TransitionError("operator_request_stage_approval_invalid")
    subordinate_bindings = []
    for item in subordinate:
        artifact_digest = str(item.get("approval_digest") or item.get("approval_semantic_digest")
                              or item.get("receipt_semantic_digest") or "")
        artifact_id = str(item.get("approval_id") or item.get("approval_evidence_id")
                          or item.get("receipt_id") or "")
        if not artifact_id or not artifact_digest:
            raise TransitionError("operator_request_subordinate_approval_invalid")
        subordinate_bindings.append({"approval_id": artifact_id, "approval_digest": artifact_digest})
    body = {"schema_version": REQUEST_SCHEMA, "installation_identity": installation_identity,
            "protocol_id": protocol["protocol_id"], "protocol_digest": protocol["protocol_digest"],
            "transition_id": protocol["transition_id"], "requested_stage": requested_stage,
            "expected_prior_phase": expected_prior_phase, "expected_journal_head": expected_journal_head,
            "stage_approval_id": approval_digest, "stage_approval_digest": approval_digest,
            "stage_approval": stage, "subordinate_approvals": subordinate,
            "stage_evidence": _plain(stage_evidence or {}),
            "subordinate_approval_bindings": subordinate_bindings, "operation_id": operation_id,
            "correlation_id": correlation_id, "operator_identity": operator_identity,
            "operator_provenance": _plain(operator_provenance), "created_at": created_at,
            "expires_at": expires_at, "grants_authority": False}
    request_digest = _digest_bytes(_canonical(body))
    return {**body, "request_id": "resident-transition-request-" + request_digest[:24],
            "request_digest": request_digest}


def persist_request(installation_root: Path, request: Mapping[str, Any]) -> Path:
    """Create one immutable packet below the fixed installation custody root."""
    if os.name != "posix":
        raise TransitionError("transition_request_publication_unsupported_platform")
    root = Path(installation_root) / REQUEST_CUSTODY
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{request['request_id']}.json"
    data = _canonical(request)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    try:
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return target


def persist_protocol(installation_root: Path, protocol: TransitionProtocol) -> Path:
    """Install one immutable exact protocol at the sole daemon custody path."""
    if os.name != "posix":
        raise TransitionError("transition_protocol_publication_unsupported_platform")
    protocol.verify()
    target = Path(installation_root) / PROTOCOL_CUSTODY
    target.parent.mkdir(parents=True, exist_ok=True)
    data = _canonical(protocol.value)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    try:
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return target


def load_verified_protocol(installation_root: Path, *, protocol_id: str,
                           protocol_digest: str) -> TransitionProtocol:
    """Load only the fixed installation protocol and verify its exact binding."""
    path = Path(installation_root) / PROTOCOL_CUSTODY
    try:
        raw = read_explicit_file(path, max_bytes=1_048_576)
        value = json.loads(raw.decode("utf-8"))
    except (WindowsHandleCustodyError, UnicodeError, json.JSONDecodeError) as exc:
        raise TransitionError("transition_protocol_missing_or_invalid") from exc
    if not isinstance(value, dict):
        raise TransitionError("transition_protocol_missing_or_invalid")
    protocol = TransitionProtocol(MappingProxyType(value))
    protocol.verify()
    if value.get("protocol_id") != protocol_id or value.get("protocol_digest") != protocol_digest:
        raise TransitionError("transition_protocol_config_binding_mismatch")
    if _canonical(value) != raw:
        raise TransitionError("transition_protocol_noncanonical")
    return protocol


def journal_identity(protocol: TransitionProtocol) -> str:
    return "resident-transition-journal-" + digest({
        "protocol_id": protocol.value["protocol_id"],
        "protocol_digest": protocol.value["protocol_digest"],
        "journal_custody": JOURNAL_CUSTODY,
    })[:24]


class LiveTransitionOperatorRuntime:
    """Observe and process at most one immutable request per explicit call."""
    def __init__(self, *, config: LiveTransitionConfig, installation_root: Path, controller: Any,
                 slot: Any, gate: Any,
                 subordinate_verifier: Callable[[str, Sequence[Mapping[str, Any]]], None] | None = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self.config, self.installation_root, self.controller = config, Path(installation_root), controller
        self.slot, self.gate, self.subordinate_verifier, self.clock = slot, gate, subordinate_verifier, clock
        self._lock = threading.Lock()
        self._latest: dict[str, Any] | None = None

    @property
    def request_root(self) -> Path:
        return self.installation_root / REQUEST_CUSTODY

    @property
    def receipt_path(self) -> Path:
        return self.installation_root / RECEIPT_CUSTODY

    def _receipts(self) -> list[dict[str, Any]]:
        try:
            raw_receipts = read_explicit_file(self.receipt_path, max_bytes=MAX_TRANSITION_RECEIPT_BYTES)
        except WindowsHandleCustodyError as exc:
            if str(exc) == "explicit_file_missing":
                return []
            raise TransitionError("operator_receipt_custody_unbounded_or_not_regular") from exc
        rows: list[dict[str, Any]] = []
        prior = "GENESIS"
        seen: set[str] = set()
        try:
            lines = raw_receipts.splitlines(keepends=True)
        except UnicodeError as exc:
            raise TransitionError("operator_receipt_custody_corrupt") from exc
        if len(lines) > MAX_TRANSITION_RECEIPTS or any(
                not line or len(line) > MAX_TRANSITION_REQUEST_BYTES for line in lines):
            raise TransitionError("operator_receipt_retention_limit_exceeded")
        for sequence, line in enumerate(lines, 1):
            try:
                row = json.loads(line.decode("utf-8"))
                claimed = row.pop("receipt_digest")
            except (TypeError, ValueError, KeyError, AttributeError, UnicodeError) as exc:
                raise TransitionError("operator_receipt_custody_corrupt") from exc
            if (not isinstance(row, dict) or set(row) != {"schema_version", "sequence", "prior_digest", "request_id", "result", "detail"}
                    or row.get("schema_version") != RECEIPT_SCHEMA or row.get("sequence") != sequence
                    or row.get("prior_digest") != prior or not isinstance(row.get("detail"), dict)
                    or row.get("result") not in {"stage_advanced", "rejected", "incomplete"}
                    or not isinstance(row.get("request_id"), str) or not row["request_id"]
                    or row["request_id"] in seen or claimed != _digest_bytes(_canonical(row))):
                raise TransitionError("operator_receipt_custody_corrupt")
            if _canonical({**row, "receipt_digest": claimed}) != line:
                raise TransitionError("operator_receipt_custody_noncanonical")
            if sequence > MAX_TRANSITION_RECEIPTS:
                raise TransitionError("operator_receipt_retention_limit_exceeded")
            row["receipt_digest"] = claimed
            rows.append(row); seen.add(row["request_id"]); prior = claimed
        return rows

    def _request_packets(self) -> tuple[dict[str, Any], ...]:
        """Read bounded immutable request packets without consuming or executing them."""
        if os.name == "nt":
            try:
                entries = read_regular_files(self.request_root, max_entries=MAX_TRANSITION_REQUESTS,
                    max_file_bytes=MAX_TRANSITION_REQUEST_BYTES,
                    max_total_bytes=MAX_TRANSITION_REQUEST_ROOT_BYTES)
            except WindowsHandleCustodyError as exc:
                if str(exc) == "explicit_file_missing":
                    return ()
                raise TransitionError("operator_request_custody_unavailable") from exc
        else:
            try:
                metadata = self.request_root.lstat()
            except FileNotFoundError:
                return ()
            except OSError as exc:
                raise TransitionError("operator_request_custody_unavailable") from exc
            if not stat.S_ISDIR(metadata.st_mode):
                raise TransitionError("operator_request_custody_not_regular")
            names: list[str] = []
            try:
                with os.scandir(self.request_root) as entries_iter:
                    for entry in entries_iter:
                        if len(names) >= MAX_TRANSITION_REQUESTS:
                            raise TransitionError("operator_request_retention_limit_exceeded")
                        names.append(entry.name)
            except OSError as exc:
                raise TransitionError("operator_request_custody_unavailable") from exc
            selected = tuple(sorted(name for name in names if name.endswith(".json")))
            entries = []
            total = 0
            for name in selected:
                try:
                    data = read_explicit_file(self.request_root / name,
                        max_bytes=MAX_TRANSITION_REQUEST_BYTES)
                except WindowsHandleCustodyError as exc:
                    raise TransitionError("operator_request_custody_unavailable") from exc
                total += len(data)
                if total > MAX_TRANSITION_REQUEST_ROOT_BYTES:
                    raise TransitionError("operator_request_retention_limit_exceeded")
                entries.append((name, data))
        packets: list[dict[str, Any]] = []
        for name, raw in entries:
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise TransitionError("operator_request_custody_corrupt") from exc
            if (not isinstance(value, dict) or name != str(value.get("request_id", "")) + ".json"
                    or _canonical(value) != raw):
                raise TransitionError("operator_request_custody_noncanonical_or_mismatched")
            self._verify_packet_identity(value)
            packets.append(value)
        return tuple(packets)

    def inspect_custody(self) -> dict[str, Any]:
        """Reconstruct request/receipt/journal posture without advancing any stage."""
        receipts = self._receipts()
        receipt_by_id = {item["request_id"]: item for item in receipts}
        journal_by_id: dict[str, list[Mapping[str, Any]]] = {}
        for entry in self.controller.journal.entries():
            evidence = entry.get("evidence")
            request = evidence.get("operator_request") if isinstance(evidence, Mapping) else None
            if isinstance(request, Mapping) and isinstance(request.get("request_id"), str):
                journal_by_id.setdefault(request["request_id"], []).append(entry)
        observations: list[dict[str, Any]] = []
        for packet in self._request_packets():
            request_id = packet["request_id"]
            protocol = self.controller.protocol.value
            if (packet.get("installation_identity") != self.config.installation_identity
                    or packet.get("protocol_id") != self.config.protocol_id
                    or packet.get("protocol_digest") != self.config.protocol_digest
                    or packet.get("transition_id") != protocol.get("transition_id")):
                raise TransitionError("operator_request_recovered_binding_mismatch")
            receipt = receipt_by_id.get(request_id)
            journal = journal_by_id.get(request_id, [])
            if receipt is not None:
                state = "receipt_recorded"
            elif journal:
                state = "transition_journal_recorded_incomplete_or_unreceipted"
            else:
                state = "request_present_unconsumed"
            observations.append({"request_id": request_id,
                "request_digest": packet["request_digest"], "transition_id": packet.get("transition_id"),
                "requested_stage": packet.get("requested_stage"), "custody_state": state,
                "receipt_digest": receipt.get("receipt_digest") if receipt else None,
                "journal_entry_digests": [entry.get("entry_digest") for entry in journal]})
        return {"schema_version": "sentientos.resident_cognitive_transition_custody_inspection:v1",
            "read_only": True, "effect_performed": False, "request_count": len(observations),
            "receipt_count": len(receipts), "requests": observations}

    def _append_receipt(self, request_id: str, result: str, detail: Mapping[str, Any]) -> dict[str, Any]:
        if os.name != "posix":
            raise TransitionError("operator_receipt_publication_unsupported_platform")
        prior = self._receipts()
        if len(prior) >= MAX_TRANSITION_RECEIPTS or request_id in {item["request_id"] for item in prior}:
            raise TransitionError("operator_receipt_identity_or_retention_conflict")
        body = {"schema_version": RECEIPT_SCHEMA, "sequence": len(prior) + 1,
                "prior_digest": prior[-1]["receipt_digest"] if prior else "GENESIS",
                "request_id": request_id, "result": result, "detail": _plain(detail)}
        receipt = {**body, "receipt_digest": _digest_bytes(_canonical(body))}
        encoded = _canonical(receipt)
        if len(encoded) > MAX_TRANSITION_REQUEST_BYTES:
            raise TransitionError("operator_receipt_record_unbounded")
        self.receipt_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.receipt_path,
            os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            metadata = os.fstat(descriptor)
            if (not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_nlink != 1
                    or metadata.st_size + len(encoded) > MAX_TRANSITION_RECEIPT_BYTES):
                raise TransitionError("operator_receipt_custody_unbounded_or_not_regular")
            view = memoryview(encoded)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise TransitionError("operator_receipt_custody_write_incomplete")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        directory = os.open(self.receipt_path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        self._latest = receipt
        return receipt

    def _recover_journal_outcome(self, packet: Mapping[str, Any]) -> dict[str, Any] | None:
        """Reconcile an operator request against the controller's durable journal.

        The journal is the stage commit point. If the process died before the
        operator receipt was appended, record that already-published outcome
        rather than invoking the stage a second time.
        """
        request = {"request_id": packet.get("request_id"),
                   "request_digest": packet.get("request_digest")}
        matches = []
        for entry in self.controller.journal.entries():
            evidence = entry.get("evidence")
            if isinstance(evidence, Mapping) and evidence.get("operator_request") == request:
                matches.append(entry)
        if not matches:
            return None
        if len(matches) not in {1, 2}:
            raise TransitionError("operator_request_journal_lineage_ambiguous")
        attempt = matches[0]
        if (attempt.get("status") != "attempted"
                or attempt.get("evidence", {}).get("attempted_stage") != packet.get("requested_stage")
                or attempt.get("evidence", {}).get("approval_digest") != packet.get("stage_approval_digest")):
            raise TransitionError("operator_request_journal_lineage_invalid")
        terminal = matches[1] if len(matches) == 2 else None
        if terminal is not None and terminal.get("phase") != attempt.get("phase"):
            raise TransitionError("operator_request_journal_lineage_invalid")
        if terminal is not None and terminal.get("status") == "completed" and terminal.get("phase") == packet.get("requested_stage"):
            result = "stage_advanced"
        else:
            result = "incomplete"
        receipt = self._append_receipt(str(packet["request_id"]), result, {
            "recovered_from_transition_journal": True,
            "attempt_entry_digest": attempt.get("entry_digest"),
            "terminal_entry_digest": terminal.get("entry_digest") if terminal is not None else None,
            "terminal_status": terminal.get("status") if terminal is not None else "missing_after_attempt",
            "requested_stage": packet.get("requested_stage"),
        })
        return {"status": result, "request_id": packet["request_id"],
                "effect_performed": False, "recovered": True,
                "receipt_digest": receipt["receipt_digest"]}

    def _validate(self, packet: Mapping[str, Any]) -> None:
        self._verify_packet_identity(packet)
        value = dict(packet)
        value.pop("request_digest", None); value.pop("request_id", None)
        health = self.controller.health()
        expected_stage = PHASES[PHASES.index(self.controller.phase) + 1] if self.controller.phase != PHASES[-1] else None
        if value.get("installation_identity") != self.config.installation_identity: raise TransitionError("operator_request_installation_mismatch")
        if (value.get("protocol_id") != self.config.protocol_id or value.get("protocol_digest") != self.config.protocol_digest): raise TransitionError("operator_request_protocol_mismatch")
        if value.get("expected_prior_phase") != self.controller.phase: raise TransitionError("operator_request_prior_phase_mismatch")
        if value.get("expected_journal_head") != health["journal_head"]: raise TransitionError("operator_request_journal_head_mismatch")
        if value.get("requested_stage") != expected_stage: raise TransitionError("operator_request_stage_skipped")
        approval = value.get("stage_approval")
        if not isinstance(approval, Mapping) or value.get("stage_approval_digest") != approval.get("approval_digest"): raise TransitionError("operator_request_stage_approval_mismatch")
        now = self.clock().astimezone(timezone.utc)
        if not _time(value.get("created_at")) <= now <= _time(value.get("expires_at")): raise TransitionError("operator_request_expired")

    @staticmethod
    def _verify_packet_identity(packet: Mapping[str, Any]) -> None:
        value = dict(packet); request_digest = value.pop("request_digest", None); request_id = value.pop("request_id", None)
        observed = _digest_bytes(_canonical(value))
        if (value.get("schema_version") != REQUEST_SCHEMA or request_digest != observed
                or request_id != "resident-transition-request-" + observed[:24]
                or value.get("grants_authority") is not False):
            raise TransitionError("operator_request_tamper")

    def process_one(self) -> dict[str, Any]:
        if not self.config.enabled:
            return {"status": "disabled", "effect_performed": False}
        if os.name != "posix":
            raise TransitionError("live_transition_processing_unsupported_platform")
        with self._lock:
            self.request_root.mkdir(parents=True, exist_ok=True)
            if self.request_root.is_symlink() or not self.request_root.is_dir():
                raise TransitionError("operator_request_custody_not_regular")
            receipts = self._receipts()
            consumed = {item["request_id"]: item for item in receipts}
            observed_consumed: str | None = None
            for packet in self._request_packets():
                request_id = packet["request_id"]
                try:
                    if request_id in consumed:
                        self._verify_packet_identity(packet)
                        observed_consumed = request_id
                        self._latest = consumed[request_id]
                        continue
                    self._verify_packet_identity(packet)
                    recovered = self._recover_journal_outcome(packet)
                    if recovered is not None:
                        return recovered
                    self._validate(packet)
                    subordinate = packet.get("subordinate_approvals", [])
                    if not isinstance(subordinate, list): raise TransitionError("operator_request_subordinate_approval_invalid")
                    if self.subordinate_verifier is not None:
                        self.subordinate_verifier(str(packet["requested_stage"]), subordinate)
                    context = TransitionStageExecutionContext.create(
                        str(packet["requested_stage"]), subordinate)
                    result = dict(self.controller.advance(approval=packet["stage_approval"],
                                                          evidence=packet.get("stage_evidence", {}),
                                                          stage_execution_context=context,
                                                          operation_context={"request_id": packet["request_id"],
                                                              "request_digest": packet["request_digest"]}))
                    receipt = self._append_receipt(request_id, "stage_advanced", result)
                    return {"status": "stage_advanced", "request_id": request_id,
                            "effect_performed": True, "stage_result": result,
                            "receipt_digest": receipt["receipt_digest"]}
                except Exception as exc:
                    code = getattr(exc, "code", type(exc).__name__)
                    if request_id in consumed:
                        raise TransitionError("consumed_operator_request_conflict") from exc
                    if isinstance(packet, Mapping):
                        try:
                            recovered = self._recover_journal_outcome(packet)
                        except Exception as recovery_exc:
                            raise TransitionError("operator_request_recovery_ambiguous") from recovery_exc
                        if recovered is not None:
                            return recovered
                    receipt = self._append_receipt(str(request_id), "rejected", {"reason": code})
                    return {"status": "rejected", "request_id": request_id, "reason": code,
                            "effect_performed": False, "receipt_digest": receipt["receipt_digest"]}
            if observed_consumed is not None:
                return {"status": "already_consumed", "request_id": observed_consumed, "effect_performed": False}
            return {"status": "no_request", "effect_performed": False}

    def status(self) -> dict[str, Any]:
        health = dict(self.controller.health())
        session = self.slot.current_controller.observed_current_session()
        return {"schema_version": "sentientos.resident_cognitive_transition_live_status:v1",
                "enabled": self.config.enabled, "configured": True,
                "protocol_id": self.config.protocol_id, "protocol_digest": self.config.protocol_digest,
                "transition_id": self.controller.protocol.value["transition_id"],
                "current_phase": health["phase"], "current_journal_head": health["journal_head"],
                "quiesced": self.gate.quiesced,
                "resident_serving_session_id": session.session_id if session else None,
                "resident_model_identity": (_plain(session.binding.get("observed_loaded_model_identity")) if session else None),
                "activation_state_digest": session.binding.get("activation_state_semantic_digest") if session else None,
                "activation_generation": session.binding.get("activation_generation") if session else None,
                "activation_receipt_id": session.binding.get("activation_receipt_id") if session else None,
                "activation_receipt_digest": session.binding.get("activation_receipt_semantic_digest") if session else None,
                "activation_predecessor_state_digest": session.binding.get("activation_predecessor_state_digest") if session else None,
                "activation_history_digest": session.binding.get("activation_history_digest") if session else None,
                "latest_consumed_request_id": self._latest.get("request_id") if self._latest else None,
                "latest_stage_result": self._latest.get("result") if self._latest else None,
                "interrupted": health["status"] == "interrupted", "complete": health["status"] == "complete",
                "read_only": True}
