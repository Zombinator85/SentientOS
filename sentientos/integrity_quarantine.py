from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from sentientos.event_stream import record_forge_event
from sentientos.integrity_incident import Incident, write_incident

QUARANTINE_PATH = Path("glow/forge/quarantine.json")


@dataclass(slots=True)
class QuarantineState:
    schema_version: int = 1
    active: bool = False
    activated_at: str | None = None
    activated_by: str | None = None
    last_incident_id: str | None = None
    freeze_forge: bool = False
    allow_automerge: bool = True
    allow_publish: bool = True
    allow_federation_sync: bool = True
    notes: list[str] | None = None
    acknowledged_at: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["notes"] = list(self.notes or [])
        return payload


@dataclass(slots=True)
class QuarantinePolicy:
    auto_activate: bool
    freeze_forge: bool
    block_automerge: bool
    block_publish: bool
    block_federation: bool


def load_policy() -> QuarantinePolicy:
    return QuarantinePolicy(
        auto_activate=os.getenv("SENTIENTOS_QUARANTINE_AUTO", "0") == "1",
        freeze_forge=os.getenv("SENTIENTOS_QUARANTINE_FREEZE_FORGE", "0") == "1",
        block_automerge=os.getenv("SENTIENTOS_QUARANTINE_BLOCK_AUTOMERGE", "1") != "0",
        block_publish=os.getenv("SENTIENTOS_QUARANTINE_BLOCK_PUBLISH", "1") != "0",
        block_federation=os.getenv("SENTIENTOS_QUARANTINE_BLOCK_FEDERATION", "0") == "1",
    )


def load_state(repo_root: Path) -> QuarantineState:
    payload = _load_json(repo_root.resolve() / QUARANTINE_PATH)
    if not payload:
        return QuarantineState()
    fields = {k: v for k, v in payload.items() if k in QuarantineState.__dataclass_fields__}
    try:
        state = QuarantineState(**fields)
    except TypeError:
        state = QuarantineState()
    if state.notes is None:
        state.notes = []
    return state


def save_state(repo_root: Path, state: QuarantineState) -> None:
    target = repo_root.resolve() / QUARANTINE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def maybe_activate_quarantine(repo_root: Path, failures: list[str], incident: Incident, *, force_activate: bool = False) -> tuple[bool, Path, QuarantineState]:
    policy = load_policy()
    state = load_state(repo_root)
    activated = False
    should_activate = force_activate or (policy.auto_activate and incident.enforcement_mode == "enforce" and failures)
    if should_activate:
        state.active = True
        state.activated_at = incident.created_at
        state.activated_by = "auto"
        state.last_incident_id = incident.incident_id
        state.freeze_forge = policy.freeze_forge
        state.allow_automerge = not policy.block_automerge
        state.allow_publish = not policy.block_publish
        state.allow_federation_sync = not policy.block_federation
        state.notes = list(state.notes or [])
        state.notes.append(f"auto:{incident.incident_id}:{','.join(sorted(set(failures)))}")
        activated = True
        record_forge_event(
            {
                "event": "integrity_quarantine_activated",
                "level": "warning",
                "incident_id": incident.incident_id,
                "triggers": sorted(set(failures)),
                "freeze_forge": state.freeze_forge,
            }
        )
    incident_path = write_incident(repo_root, incident, quarantine_activated=activated)
    if not activated:
        record_forge_event(
            {
                "event": "integrity_incident_recorded",
                "level": "warning" if incident.severity != "critical" else "error",
                "incident_id": incident.incident_id,
                "triggers": incident.triggers,
                "enforcement_mode": incident.enforcement_mode,
            }
        )
    save_state(repo_root, state)
    return activated, incident_path, state


def acknowledge(repo_root: Path, note: str) -> QuarantineState:
    state = load_state(repo_root)
    state.notes = list(state.notes or [])
    state.notes.append(f"ack:{_iso_now()}:{note}")
    state.acknowledged_at = _iso_now()
    save_state(repo_root, state)
    return state


def clear(repo_root: Path, note: str) -> QuarantineState:
    state = load_state(repo_root)
    state.active = False
    state.freeze_forge = False
    state.allow_automerge = True
    state.allow_publish = True
    state.allow_federation_sync = True
    state.notes = list(state.notes or [])
    state.notes.append(f"clear:{_iso_now()}:{note}")
    save_state(repo_root, state)
    return state


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
