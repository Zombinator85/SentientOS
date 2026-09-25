"""Installation-custodied operator ingress for one resident transition stage.

The mailbox is a request transport, never an authority source.  The transition
controller remains responsible for verifying the exact stage approval and all
subordinate owners retain their independent admissions.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .resident_cognitive_model_transition_experiment import PHASES, TransitionError, digest

CONFIG_SCHEMA = "sentientos.resident_cognitive_transition_live_config:v1"
REQUEST_SCHEMA = "sentientos.resident_cognitive_transition_operator_request:v1"
RECEIPT_SCHEMA = "sentientos.resident_cognitive_transition_operator_request_receipt:v1"
REQUEST_CUSTODY = "state/resident-cognitive-transition/operator-requests"
RECEIPT_CUSTODY = "state/resident-cognitive-transition/operator-request-receipts.jsonl"
JOURNAL_CUSTODY = "state/resident-cognitive-transition/transition.journal.jsonl"


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
        value = json.loads(Path(path).read_text(encoding="utf-8"))
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
        artifact_digest = str(item.get("approval_digest") or item.get("receipt_semantic_digest") or "")
        artifact_id = str(item.get("approval_id") or item.get("receipt_id") or "")
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
        if not self.receipt_path.exists():
            return []
        return [json.loads(line) for line in self.receipt_path.read_text(encoding="utf-8").splitlines()]

    def _append_receipt(self, request_id: str, result: str, detail: Mapping[str, Any]) -> dict[str, Any]:
        prior = self._receipts()
        body = {"schema_version": RECEIPT_SCHEMA, "sequence": len(prior) + 1,
                "prior_digest": prior[-1]["receipt_digest"] if prior else "GENESIS",
                "request_id": request_id, "result": result, "detail": _plain(detail)}
        receipt = {**body, "receipt_digest": _digest_bytes(_canonical(body))}
        self.receipt_path.parent.mkdir(parents=True, exist_ok=True)
        with self.receipt_path.open("a", encoding="utf-8") as stream:
            stream.write(_canonical(receipt).decode())
            stream.flush(); os.fsync(stream.fileno())
        self._latest = receipt
        return receipt

    def _validate(self, packet: Mapping[str, Any]) -> None:
        value = dict(packet); request_digest = value.pop("request_digest", None); request_id = value.pop("request_id", None)
        observed = _digest_bytes(_canonical(value))
        if (value.get("schema_version") != REQUEST_SCHEMA or request_digest != observed
                or request_id != "resident-transition-request-" + observed[:24]
                or value.get("grants_authority") is not False):
            raise TransitionError("operator_request_tamper")
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

    def process_one(self) -> dict[str, Any]:
        if not self.config.enabled:
            return {"status": "disabled", "effect_performed": False}
        with self._lock:
            self.request_root.mkdir(parents=True, exist_ok=True)
            consumed = {item["request_id"] for item in self._receipts()}
            observed_consumed: str | None = None
            for path in sorted(self.request_root.glob("*.json")):
                try:
                    packet = json.loads(path.read_text(encoding="utf-8"))
                    request_id = str(packet.get("request_id", "malformed:" + _digest_bytes(path.read_bytes())[:24]))
                    if request_id in consumed:
                        observed_consumed = request_id
                        self._latest = next(item for item in reversed(self._receipts()) if item["request_id"] == request_id)
                        continue
                    self._validate(packet)
                    subordinate = packet.get("subordinate_approvals", [])
                    if not isinstance(subordinate, list): raise TransitionError("operator_request_subordinate_approval_invalid")
                    if self.subordinate_verifier is not None:
                        self.subordinate_verifier(str(packet["requested_stage"]), subordinate)
                    result = dict(self.controller.advance(approval=packet["stage_approval"],
                                                          evidence=packet.get("stage_evidence", {})))
                    receipt = self._append_receipt(request_id, "stage_advanced", result)
                    return {"status": "stage_advanced", "request_id": request_id,
                            "effect_performed": True, "stage_result": result,
                            "receipt_digest": receipt["receipt_digest"]}
                except Exception as exc:
                    code = getattr(exc, "code", type(exc).__name__)
                    request_id = locals().get("request_id", "malformed:" + _digest_bytes(path.read_bytes())[:24])
                    receipt = self._append_receipt(str(request_id), "rejected", {"reason": code})
                    return {"status": "rejected", "request_id": request_id, "reason": code,
                            "effect_performed": False, "receipt_digest": receipt["receipt_digest"]}
            if observed_consumed is not None:
                return {"status": "already_consumed", "request_id": observed_consumed, "effect_performed": False}
            return {"status": "no_request", "effect_performed": False}

    def status(self) -> dict[str, Any]:
        health = dict(self.controller.health())
        session = self.slot.current_controller.current_session()
        return {"schema_version": "sentientos.resident_cognitive_transition_live_status:v1",
                "enabled": self.config.enabled, "configured": True,
                "protocol_id": self.config.protocol_id, "protocol_digest": self.config.protocol_digest,
                "transition_id": self.controller.protocol.value["transition_id"],
                "current_phase": health["phase"], "current_journal_head": health["journal_head"],
                "quiesced": self.gate.quiesced,
                "resident_serving_session_id": session.session_id if session else None,
                "resident_model_identity": (_plain(session.binding.get("observed_loaded_model_identity")) if session else None),
                "latest_consumed_request_id": self._latest.get("request_id") if self._latest else None,
                "latest_stage_result": self._latest.get("result") if self._latest else None,
                "interrupted": health["status"] == "interrupted", "complete": health["status"] == "complete",
                "read_only": True}
