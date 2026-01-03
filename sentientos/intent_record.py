from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, MutableMapping

from logging_config import get_log_path
from log_utils import append_json, read_json
from policy_digest import policy_digest_reference

INTENT_LOG_PATH = get_log_path("intent_records.jsonl", "INTENT_RECORD_LOG")


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _payload_fingerprint(payload: object) -> str:
    serialised = _canonical_json(payload)
    return sha256(serialised.encode("utf-8")).hexdigest()


def _intent_identity_payload(
    *,
    intent_type: str,
    payload_fingerprint: str,
    originating_context: str,
) -> Mapping[str, str]:
    return {
        "intent_type": intent_type,
        "payload_fingerprint": payload_fingerprint,
        "originating_context": originating_context,
    }


def _build_intent_id(
    *,
    intent_type: str,
    payload_fingerprint: str,
    originating_context: str,
) -> str:
    payload = _intent_identity_payload(
        intent_type=intent_type,
        payload_fingerprint=payload_fingerprint,
        originating_context=originating_context,
    )
    serialised = _canonical_json(payload)
    return sha256(serialised.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class IntentRecord:
    """Non-authoritative intent capture for audit and reasoning only."""

    intent_id: str
    intent_type: str
    payload_fingerprint: str
    originating_context: str
    policy_reference: Mapping[str, str] = field(compare=False, hash=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "policy_reference",
            MappingProxyType(dict(self.policy_reference)),
        )

    def canonical_payload(self) -> MutableMapping[str, object]:
        return {
            "intent_id": self.intent_id,
            "intent_type": self.intent_type,
            "payload_fingerprint": self.payload_fingerprint,
            "originating_context": self.originating_context,
            "policy_reference": dict(self.policy_reference),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.canonical_payload())


def build_intent_record(
    *,
    intent_type: str,
    payload: object,
    originating_context: str,
    policy_reference: Mapping[str, str] | None = None,
    intent_id: str | None = None,
) -> IntentRecord:
    payload_fingerprint = _payload_fingerprint(payload)
    resolved_intent_id = intent_id or _build_intent_id(
        intent_type=intent_type,
        payload_fingerprint=payload_fingerprint,
        originating_context=originating_context,
    )
    return IntentRecord(
        intent_id=resolved_intent_id,
        intent_type=intent_type,
        payload_fingerprint=payload_fingerprint,
        originating_context=originating_context,
        policy_reference=policy_reference or policy_digest_reference(),
    )


def emit_intent_record(record: IntentRecord, *, log_path: Path | None = None) -> None:
    """Emit an intent record without altering execution authority."""

    try:
        append_json(Path(log_path or INTENT_LOG_PATH), record.canonical_payload())
    except Exception:
        return


def capture_intent_record(
    *,
    intent_type: str,
    payload: object,
    originating_context: str,
    policy_reference: Mapping[str, str] | None = None,
    log_path: Path | None = None,
) -> IntentRecord | None:
    """Intent ≠ permission. Captures attempted actions for audit without authorizing them."""

    try:
        record = build_intent_record(
            intent_type=intent_type,
            payload=payload,
            originating_context=originating_context,
            policy_reference=policy_reference,
        )
    except Exception:
        return None
    emit_intent_record(record, log_path=log_path)
    return record


def read_intent_records(log_path: Path | None = None) -> list[dict[str, object]]:
    return read_json(Path(log_path or INTENT_LOG_PATH))


__all__ = [
    "IntentRecord",
    "build_intent_record",
    "capture_intent_record",
    "emit_intent_record",
    "read_intent_records",
]
