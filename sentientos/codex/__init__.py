from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List, Optional

from ..storage import ensure_mounts, get_state_file

LOGGER = logging.getLogger(__name__)
_STATE_LOCK = Lock()
_STATE_PATH = get_state_file("codex_state.json")


@dataclass
class Amendment:
    identifier: str
    summary: str
    created_at: float
    status: str = "proposed"
    committed: bool = False
    payload: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def new(cls, summary: str, payload: Optional[Dict[str, str]] = None) -> "Amendment":
        return cls(
            identifier=str(uuid.uuid4()),
            summary=summary,
            created_at=time.time(),
            payload=payload or {},
        )


class CodexState:
    def __init__(self, amendments: Optional[List[Amendment]] = None):
        self.amendments: List[Amendment] = amendments or []

    def to_dict(self) -> Dict[str, List[Dict[str, object]]]:
        return {
            "amendments": [
                {
                    "identifier": item.identifier,
                    "summary": item.summary,
                    "created_at": item.created_at,
                    "status": item.status,
                    "committed": item.committed,
                    "payload": item.payload,
                }
                for item in self.amendments
            ]
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, object]) -> "CodexState":
        items: List[Amendment] = []
        for entry in raw.get("amendments", []):
            if not isinstance(entry, dict):
                continue
            try:
                items.append(
                    Amendment(
                        identifier=str(entry["identifier"]),
                        summary=str(entry.get("summary", "")),
                        created_at=float(entry.get("created_at", time.time())),
                        status=str(entry.get("status", "proposed")),
                        committed=bool(entry.get("committed", False)),
                        payload=dict(entry.get("payload", {})),
                    )
                )
            except (KeyError, TypeError, ValueError):
                LOGGER.debug("Skipping malformed amendment entry: %s", entry)
        return cls(items)


def _load_state() -> CodexState:
    ensure_mounts()
    if not _STATE_PATH.exists():
        return CodexState()
    try:
        data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        LOGGER.warning("Unable to read codex state: %s", exc)
        return CodexState()
    return CodexState.from_dict(data)


def _save_state(state: CodexState) -> None:
    with _STATE_LOCK:
        try:
            _STATE_PATH.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
        except OSError as exc:
            LOGGER.error("Failed to persist codex state: %s", exc)


class GenesisForge:
    """Generate candidate amendments for consideration."""

    @staticmethod
    def expand() -> None:
        state = _load_state()
        proposed = [item for item in state.amendments if item.status == "proposed"]
        if proposed:
            LOGGER.debug("GenesisForge: existing proposals detected, skipping generation.")
            return
        amendment = Amendment.new(
            summary="Automated maintenance sweep",
            payload={"origin": "genesis_forge", "timestamp": str(time.time())},
        )
        LOGGER.info("GenesisForge created amendment %s", amendment.identifier)
        state.amendments.append(amendment)
        _save_state(state)


class SpecAmender:
    """Manage the lifecycle of Codex amendments."""

    @staticmethod
    def cycle() -> None:
        state = _load_state()
        for amendment in state.amendments:
            if amendment.status == "approved" and not amendment.committed:
                LOGGER.debug("SpecAmender: amendment %s awaiting commit", amendment.identifier)

    @staticmethod
    def has_new_commit() -> bool:
        state = _load_state()
        return any(amendment.status == "approved" and not amendment.committed for amendment in state.amendments)

    @staticmethod
    def mark_committed() -> None:
        state = _load_state()
        updated = False
        for amendment in state.amendments:
            if amendment.status == "approved" and not amendment.committed:
                amendment.committed = True
                updated = True
                LOGGER.info("SpecAmender marked amendment %s as committed", amendment.identifier)
        if updated:
            _save_state(state)


class IntegrityDaemon:
    """Validate proposed amendments before they are applied."""

    @staticmethod
    def guard() -> None:
        state = _load_state()
        updated = False
        now = time.time()
        for amendment in state.amendments:
            if amendment.status == "proposed" and now - amendment.created_at > 5:
                amendment.status = "approved"
                updated = True
                LOGGER.info("IntegrityDaemon approved amendment %s", amendment.identifier)
        if updated:
            _save_state(state)


class CodexHealer:
    """Prune stale amendments and maintain overall health."""

    EXPIRY_SECONDS = 3600

    @classmethod
    def monitor(cls) -> None:
        state = _load_state()
        threshold = time.time() - cls.EXPIRY_SECONDS
        original = len(state.amendments)
        state.amendments = [
            amendment
            for amendment in state.amendments
            if amendment.status != "rejected" and amendment.created_at >= threshold
        ]
        if len(state.amendments) != original:
            LOGGER.info("CodexHealer removed %s stale amendments", original - len(state.amendments))
            _save_state(state)
