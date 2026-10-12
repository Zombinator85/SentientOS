from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any

from sentientos.strategic_posture import derived_thresholds, env_int, resolve_posture
from sentientos.private_file_custody import (
    PrivateFileCustodyError, open_private_directory, read_private_file_at,
)
from sentientos.windows_handle_custody import (
    WindowsHandleCustodyError, read_explicit_file,
)

PRESSURE_STATE_PATH = Path("glow/forge/integrity_pressure_state.json")
INCIDENT_FEED_PATH = Path("pulse/integrity_incidents.jsonl")
MAX_INCIDENT_FEED_BYTES = 1_048_576
MAX_INCIDENT_ROWS = 4096
MAX_INCIDENT_ROW_BYTES = 65_536
MAX_TRIGGERS_PER_INCIDENT = 512
MAX_TRIGGER_CHARS = 512


class IntegrityPressureInputError(ValueError):
    """The incident feed cannot safely support a bounded pressure calculation."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(slots=True)
class IntegrityPressureMetrics:
    incidents_last_1h: int
    incidents_last_24h: int
    enforced_failures_last_24h: int
    unique_trigger_types_last_24h: int
    quarantine_activations_last_24h: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(slots=True)
class IntegrityPressureSnapshot:
    level: int
    metrics: IntegrityPressureMetrics
    warn_threshold: int
    enforce_threshold: int
    critical_threshold: int
    strategic_posture: str
    checked_at: str


@dataclass(slots=True)
class IntegrityPressureState:
    schema_version: int = 1
    level: int = 0
    strategic_posture: str = "balanced"
    last_pressure_change_at: str | None = None
    posture_last_changed_at: str | None = None


def compute_integrity_pressure(repo_root: Path, *, now: datetime | None = None) -> IntegrityPressureSnapshot:
    at = now or datetime.now(timezone.utc)
    rows = _read_incidents(repo_root.resolve() / INCIDENT_FEED_PATH)
    one_hour = at - timedelta(hours=1)
    day = at - timedelta(hours=24)

    incidents_last_1h = 0
    incidents_last_24h = 0
    enforced_failures_last_24h = 0
    unique_triggers: set[str] = set()
    quarantine_activations_last_24h = 0
    for row in rows:
        created_at = _parse_iso(row.get("created_at"))
        if created_at is None:
            continue
        if created_at >= one_hour:
            incidents_last_1h += 1
        if created_at < day:
            continue
        incidents_last_24h += 1
        if str(row.get("enforcement_mode", "")).lower() == "enforce":
            enforced_failures_last_24h += 1
        if bool(row.get("quarantine_activated", False)):
            quarantine_activations_last_24h += 1
        raw_triggers = row.get("triggers")
        if isinstance(raw_triggers, list):
            for trigger in raw_triggers:
                if isinstance(trigger, str) and trigger:
                    unique_triggers.add(trigger)

    metrics = IntegrityPressureMetrics(
        incidents_last_1h=incidents_last_1h,
        incidents_last_24h=incidents_last_24h,
        enforced_failures_last_24h=enforced_failures_last_24h,
        unique_trigger_types_last_24h=len(unique_triggers),
        quarantine_activations_last_24h=quarantine_activations_last_24h,
    )
    posture = resolve_posture()
    defaults = derived_thresholds(posture, warn_base=3, enforce_base=7, critical_base=12)
    warn_threshold = _env_int("SENTIENTOS_PRESSURE_WARN_THRESHOLD", defaults["warn"])
    enforce_threshold = _env_int("SENTIENTOS_PRESSURE_ENFORCE_THRESHOLD", defaults["enforce"])
    critical_threshold = _env_int("SENTIENTOS_PRESSURE_CRITICAL_THRESHOLD", defaults["critical"])

    level = 0
    score = metrics.incidents_last_24h + metrics.enforced_failures_last_24h + metrics.quarantine_activations_last_24h + metrics.unique_trigger_types_last_24h
    if score >= critical_threshold:
        level = 3
    elif score >= enforce_threshold:
        level = 2
    elif score >= warn_threshold:
        level = 1

    return IntegrityPressureSnapshot(
        level=level,
        metrics=metrics,
        warn_threshold=warn_threshold,
        enforce_threshold=enforce_threshold,
        critical_threshold=critical_threshold,
        strategic_posture=posture.posture,
        checked_at=at.isoformat().replace("+00:00", "Z"),
    )


def escalation_disabled() -> bool:
    return os.getenv("SENTIENTOS_PRESSURE_DISABLE_ESCALATION", "0") == "1"


def apply_escalation(level: int, *, gate_name: str, base_enforce: bool, base_warn: bool, high_severity: bool) -> tuple[bool, bool]:
    if escalation_disabled():
        return base_enforce, base_warn
    enforce = base_enforce
    warn = base_warn
    if level >= 1:
        warn = True
    posture = resolve_posture()
    if level >= posture.high_severity_enforce_level and high_severity:
        enforce = True
    _ = gate_name
    return enforce, warn


def should_force_quarantine(level: int) -> bool:
    if escalation_disabled():
        return False
    posture = resolve_posture()
    return level >= posture.quarantine_force_level


def load_pressure_state(repo_root: Path) -> IntegrityPressureState:
    payload = _load_json(repo_root.resolve() / PRESSURE_STATE_PATH)
    fields = {k: v for k, v in payload.items() if k in IntegrityPressureState.__dataclass_fields__}
    try:
        return IntegrityPressureState(**fields)
    except TypeError:
        return IntegrityPressureState()


def save_pressure_state(repo_root: Path, state: IntegrityPressureState) -> None:
    target = repo_root.resolve() / PRESSURE_STATE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(state), sort_keys=True, indent=2) + "\n", encoding="utf-8")


def update_pressure_state(repo_root: Path, snapshot: IntegrityPressureSnapshot) -> tuple[IntegrityPressureState, bool]:
    state = load_pressure_state(repo_root)
    changed = snapshot.level != state.level
    posture_changed = snapshot.strategic_posture != state.strategic_posture
    if changed:
        state.level = snapshot.level
        state.last_pressure_change_at = snapshot.checked_at
    if posture_changed:
        state.strategic_posture = snapshot.strategic_posture
        state.posture_last_changed_at = snapshot.checked_at
    if changed or posture_changed:
        save_pressure_state(repo_root, state)
    return state, changed or posture_changed


def _read_incidents(path: Path) -> list[dict[str, object]]:
    if os.name == "posix":
        try:
            directory_fd = open_private_directory(path.parent, create=False)
        except PrivateFileCustodyError as exc:
            if str(exc) == "directory_root_missing":
                return []
            raise IntegrityPressureInputError("incident_feed_custody_unavailable") from exc
        try:
            try:
                data = read_private_file_at(directory_fd, path.name,
                    max_bytes=MAX_INCIDENT_FEED_BYTES, require_private_mode=False,
                    require_owner_read=True)
            except PrivateFileCustodyError as exc:
                if str(exc) == "file_missing":
                    return []
                if str(exc) == "file_unbounded_or_not_private":
                    raise IntegrityPressureInputError(
                        "incident_feed_size_or_custody_invalid") from exc
                raise IntegrityPressureInputError("incident_feed_custody_unavailable") from exc
        finally:
            os.close(directory_fd)
    elif os.name == "nt":
        try:
            data = read_explicit_file(path, max_bytes=MAX_INCIDENT_FEED_BYTES,
                require_private_acl=True)
        except WindowsHandleCustodyError as exc:
            if str(exc) == "explicit_file_missing":
                return []
            if str(exc) in {"explicit_file_changed_during_open", "explicit_file_changed_during_read"}:
                raise IntegrityPressureInputError("incident_feed_size_or_stability_invalid") from exc
            if str(exc) == "explicit_file_path_invalid":
                raise IntegrityPressureInputError("incident_feed_path_invalid") from exc
            raise IntegrityPressureInputError("incident_feed_custody_unavailable") from exc
    else:
        raise IntegrityPressureInputError("incident_feed_custody_unsupported")
    return parse_bounded_incident_feed(data)


def parse_bounded_incident_feed(data: bytes) -> list[dict[str, object]]:
    """Apply the pressure reader's exact byte, row, and semantic bounds to bytes."""
    if not isinstance(data, bytes):
        raise IntegrityPressureInputError("incident_feed_bytes_invalid")
    if len(data) > MAX_INCIDENT_FEED_BYTES:
        raise IntegrityPressureInputError("incident_feed_size_limit_exceeded")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise IntegrityPressureInputError("incident_feed_utf8_invalid") from exc
    rows: list[dict[str, object]] = []
    lines = text.splitlines()
    if len(lines) > MAX_INCIDENT_ROWS:
        raise IntegrityPressureInputError("incident_feed_row_limit_exceeded")
    for line in lines:
        if len(line.encode("utf-8")) > MAX_INCIDENT_ROW_BYTES:
            raise IntegrityPressureInputError("incident_feed_row_size_limit_exceeded")
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped,
                object_pairs_hook=_reject_duplicate_object_keys,
                parse_constant=_reject_json_constant)
        except (json.JSONDecodeError, ValueError) as exc:
            raise IntegrityPressureInputError("incident_feed_row_invalid") from exc
        if not isinstance(payload, dict):
            raise IntegrityPressureInputError("incident_feed_row_not_object")
        if _parse_iso(payload.get("created_at")) is None:
            raise IntegrityPressureInputError("incident_feed_event_time_invalid")
        if ("enforcement_mode" in payload
                and not isinstance(payload["enforcement_mode"], str)):
            raise IntegrityPressureInputError("incident_feed_enforcement_mode_invalid")
        if ("quarantine_activated" in payload
                and type(payload["quarantine_activated"]) is not bool):
            raise IntegrityPressureInputError("incident_feed_quarantine_flag_invalid")
        triggers = payload.get("triggers")
        if triggers is not None:
            if not isinstance(triggers, list):
                raise IntegrityPressureInputError("incident_feed_triggers_invalid")
            if len(triggers) > MAX_TRIGGERS_PER_INCIDENT:
                raise IntegrityPressureInputError("incident_feed_trigger_limit_exceeded")
            if any(not isinstance(item, str) for item in triggers):
                raise IntegrityPressureInputError("incident_feed_triggers_invalid")
            if any(len(item) > MAX_TRIGGER_CHARS for item in triggers):
                raise IntegrityPressureInputError("incident_feed_trigger_limit_exceeded")
        rows.append(payload)
    return rows


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_object_key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError("non_finite_json_number:" + value)


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _env_int(name: str, default: int) -> int:
    override = env_int(name)
    if override is not None:
        return max(0, override)
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default
