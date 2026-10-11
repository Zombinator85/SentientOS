"""Protective quarantine state with fail-closed, bounded filesystem custody.

Quarantine evidence has three distinct read outcomes: first-use absence, a
validated v1 record, and invalid/unavailable custody.  The last outcome is
never converted into an inactive state.  This module owns no effect authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import json
import hashlib
import os
from pathlib import Path
from typing import Any, NoReturn

from sentientos.event_stream import record_forge_event
from sentientos.integrity_incident import Incident, write_incident
from sentientos.private_file_custody import (
    PrivateFileCustodyError,
    open_private_directory,
    publish_immutable_bytes,
    read_private_file_at,
    replace_private_bytes_with_status,
)
from sentientos.strategic_posture import env_bool, resolve_posture
from sentientos.windows_handle_custody import (
    WindowsHandleCustodyError,
    read_explicit_file,
    verify_explicit_directory,
)

QUARANTINE_PATH = Path("glow/forge/quarantine.json")
MAX_QUARANTINE_BYTES = 262_144
PENDING_SUFFIX = ".pending"


class QuarantineStateError(RuntimeError):
    """Quarantine state was not safely readable or semantically valid."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class QuarantinePublicationUncertain(QuarantineStateError):
    """Atomic replacement is visible but directory durability is unproven."""


class QuarantineCustodyStatus(str, Enum):
    FIRST_USE_ABSENT = "first_use_absent"
    VALID_V1 = "valid_v1"


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


@dataclass(frozen=True, slots=True)
class QuarantineStateLoad:
    state: QuarantineState
    custody_status: QuarantineCustodyStatus


@dataclass(slots=True)
class QuarantinePolicy:
    auto_activate: bool
    freeze_forge: bool
    block_automerge: bool
    block_publish: bool
    block_federation: bool


def load_policy() -> QuarantinePolicy:
    posture = resolve_posture()
    auto_default = "1" if posture.quarantine_auto_sensitivity == "strict" else "0"
    freeze_default = "1" if posture.quarantine_auto_sensitivity == "strict" else "0"
    block_federation_default = "1" if posture.quarantine_auto_sensitivity == "strict" else "0"
    auto_override = env_bool("SENTIENTOS_QUARANTINE_AUTO")
    freeze_override = env_bool("SENTIENTOS_QUARANTINE_FREEZE_FORGE")
    block_automerge_override = env_bool("SENTIENTOS_QUARANTINE_BLOCK_AUTOMERGE")
    block_publish_override = env_bool("SENTIENTOS_QUARANTINE_BLOCK_PUBLISH")
    block_federation_override = env_bool("SENTIENTOS_QUARANTINE_BLOCK_FEDERATION")
    return QuarantinePolicy(
        auto_activate=(os.getenv("SENTIENTOS_QUARANTINE_AUTO", auto_default) == "1") if auto_override is None else auto_override,
        freeze_forge=(os.getenv("SENTIENTOS_QUARANTINE_FREEZE_FORGE", freeze_default) == "1") if freeze_override is None else freeze_override,
        block_automerge=(os.getenv("SENTIENTOS_QUARANTINE_BLOCK_AUTOMERGE", "1") != "0") if block_automerge_override is None else block_automerge_override,
        block_publish=(os.getenv("SENTIENTOS_QUARANTINE_BLOCK_PUBLISH", "1") != "0") if block_publish_override is None else block_publish_override,
        block_federation=(os.getenv("SENTIENTOS_QUARANTINE_BLOCK_FEDERATION", block_federation_default) == "1") if block_federation_override is None else block_federation_override,
    )


def load_state(repo_root: Path) -> QuarantineState:
    """Load only validated custody; absent state is the sole default case."""
    return load_state_with_status(repo_root).state


def load_state_with_status(repo_root: Path) -> QuarantineStateLoad:
    target = Path(os.path.abspath(os.fspath(repo_root))) / QUARANTINE_PATH
    try:
        payload = _read_state_bytes(target, repo_root=Path(os.path.abspath(os.fspath(repo_root))))
    except QuarantineStateError:
        raise
    if payload is None:
        return QuarantineStateLoad(QuarantineState(), QuarantineCustodyStatus.FIRST_USE_ABSENT)
    return QuarantineStateLoad(
        _decode_state(payload), QuarantineCustodyStatus.VALID_V1
    )


def save_state(repo_root: Path, state: QuarantineState) -> None:
    target = Path(os.path.abspath(os.fspath(repo_root))) / QUARANTINE_PATH
    # Reconcile current custody before any publication. An invalid existing
    # record or unresolved publication is evidence to preserve, never a slot
    # that a default/clear write may repair.
    load_state_with_status(repo_root)
    body = state.to_dict()
    _validate_state_payload(body)
    encoded = (json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_QUARANTINE_BYTES:
        raise QuarantineStateError("quarantine_payload_too_large")
    pending_path = _pending_path(target)
    marker = (json.dumps({"schema_version": 1, "candidate_sha256": hashlib.sha256(encoded).hexdigest()},
        sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    marker_created = False
    try:
        created = publish_immutable_bytes(pending_path, marker, max_bytes=1024,
            collision_code="quarantine_publication_marker_conflict")
        if not created:
            raise QuarantineStateError("quarantine_publication_recovery_required")
        marker_created = True
        durable = replace_private_bytes_with_status(target, encoded, max_bytes=MAX_QUARANTINE_BYTES)
    except PrivateFileCustodyError as exc:
        if marker_created:
            _remove_pending_marker(pending_path)
        raise QuarantineStateError(f"quarantine_publication_{exc.code}") from exc
    except QuarantineStateError:
        raise
    except Exception as exc:
        if marker_created:
            _remove_pending_marker(pending_path)
        raise QuarantineStateError("quarantine_publication_failed") from exc
    if not durable:
        raise QuarantinePublicationUncertain("quarantine_publication_durability_uncertain")
    try:
        _remove_pending_marker(pending_path)
    except QuarantineStateError as exc:
        raise QuarantinePublicationUncertain("quarantine_publication_marker_cleanup_uncertain") from exc


def maybe_activate_quarantine(repo_root: Path, failures: list[str], incident: Incident, *, force_activate: bool = False) -> tuple[bool, Path, QuarantineState]:
    policy = load_policy()
    posture = resolve_posture()
    state = load_state(repo_root)
    activated = False
    mode_match = incident.enforcement_mode == "enforce" if posture.quarantine_auto_sensitivity != "lenient" else incident.enforcement_mode in {"enforce", "warn"}
    should_activate = force_activate or (policy.auto_activate and mode_match and failures)
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


def _read_state_bytes(target: Path, *, repo_root: Path) -> bytes | None:
    if not repo_root.is_absolute() or not repo_root.name:
        raise QuarantineStateError("quarantine_repo_root_invalid")
    if os.name == "nt":
        try:
            verify_explicit_directory(repo_root)
            try:
                read_explicit_file(_pending_path(target), max_bytes=1024,
                    require_private_acl=True)
            except WindowsHandleCustodyError as marker_error:
                if marker_error.code != "explicit_file_missing":
                    raise
            else:
                raise QuarantineStateError("quarantine_publication_recovery_required")
            return read_explicit_file(target, max_bytes=MAX_QUARANTINE_BYTES,
                require_private_acl=True)
        except QuarantineStateError:
            raise
        except WindowsHandleCustodyError as exc:
            if exc.code == "explicit_file_missing":
                return None
            raise QuarantineStateError(f"quarantine_custody_{exc.code}") from exc
    try:
        root_fd = open_private_directory(repo_root, create=False)
    except PrivateFileCustodyError as exc:
        raise QuarantineStateError(f"quarantine_repo_root_{exc.code}") from exc
    os.close(root_fd)
    try:
        directory_fd = open_private_directory(target.parent, create=False)
    except PrivateFileCustodyError as exc:
        if exc.code == "directory_root_missing":
            return None
        raise QuarantineStateError(f"quarantine_custody_{exc.code}") from exc
    try:
        try:
            try:
                read_private_file_at(directory_fd, _pending_path(target).name,
                    max_bytes=1024, require_private_mode=True)
            except PrivateFileCustodyError as marker_error:
                if marker_error.code != "file_missing":
                    raise QuarantineStateError(f"quarantine_pending_marker_{marker_error.code}") from marker_error
            else:
                raise QuarantineStateError("quarantine_publication_recovery_required")
            return read_private_file_at(directory_fd, target.name,
                max_bytes=MAX_QUARANTINE_BYTES, require_private_mode=False,
                require_owner_read=True)
        except PrivateFileCustodyError as exc:
            if exc.code == "file_missing":
                return None
            raise QuarantineStateError(f"quarantine_custody_{exc.code}") from exc
        finally:
            os.close(directory_fd)
    except QuarantineStateError:
        raise


def _decode_state(raw: bytes) -> QuarantineState:
    try:
        payload = json.loads(raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except QuarantineStateError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise QuarantineStateError("quarantine_json_invalid") from exc
    _validate_state_payload(payload)
    try:
        return QuarantineState(**payload)
    except (TypeError, ValueError) as exc:
        raise QuarantineStateError("quarantine_fields_invalid") from exc


def _pending_path(target: Path) -> Path:
    return target.with_name(target.name + PENDING_SUFFIX)


def _remove_pending_marker(path: Path) -> None:
    """Remove only the exact private marker and persist the directory entry."""
    if os.name != "posix":
        raise QuarantineStateError("quarantine_pending_marker_cleanup_unsupported")
    try:
        directory_fd = open_private_directory(path.parent, create=False)
    except PrivateFileCustodyError as exc:
        if exc.code == "directory_root_missing":
            return
        raise QuarantineStateError(f"quarantine_pending_marker_directory_{exc.code}") from exc
    try:
        try:
            read_private_file_at(directory_fd, path.name, max_bytes=1024,
                require_private_mode=True)
        except PrivateFileCustodyError as exc:
            if exc.code == "file_missing":
                return
            raise QuarantineStateError(f"quarantine_pending_marker_{exc.code}") from exc
        try:
            os.unlink(path.name, dir_fd=directory_fd)
            os.fsync(directory_fd)
        except OSError as exc:
            raise QuarantineStateError("quarantine_pending_marker_durability_uncertain") from exc
    finally:
        try:
            os.close(directory_fd)
        except OSError as exc:
            raise QuarantineStateError("quarantine_pending_marker_close_uncertain") from exc


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise QuarantineStateError("quarantine_duplicate_json_key")
        payload[key] = value
    return payload


def _reject_constant(value: str) -> NoReturn:
    raise QuarantineStateError("quarantine_json_constant_invalid")


_REQUIRED_V1_FIELDS = frozenset({
    "schema_version", "active", "freeze_forge", "allow_automerge",
    "allow_publish", "allow_federation_sync", "notes",
})
_OPTIONAL_V1_FIELDS = frozenset({
    "activated_at", "activated_by", "last_incident_id", "acknowledged_at",
})
_BOOLEAN_FIELDS = frozenset({
    "active", "freeze_forge", "allow_automerge", "allow_publish",
    "allow_federation_sync",
})
_STRING_OR_NONE_FIELDS = _OPTIONAL_V1_FIELDS


def _validate_state_payload(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise QuarantineStateError("quarantine_object_required")
    keys = frozenset(payload)
    if not _REQUIRED_V1_FIELDS.issubset(keys) or keys - (_REQUIRED_V1_FIELDS | _OPTIONAL_V1_FIELDS):
        raise QuarantineStateError("quarantine_fields_incomplete_or_unexpected")
    if type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        raise QuarantineStateError("quarantine_schema_unsupported")
    if any(type(payload.get(name)) is not bool for name in _BOOLEAN_FIELDS):
        raise QuarantineStateError("quarantine_boolean_type_invalid")
    if any(name in payload and payload[name] is not None and not isinstance(payload[name], str)
           for name in _STRING_OR_NONE_FIELDS):
        raise QuarantineStateError("quarantine_string_field_invalid")
    notes = payload.get("notes")
    if not isinstance(notes, list) or any(not isinstance(note, str) for note in notes):
        raise QuarantineStateError("quarantine_notes_invalid")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
