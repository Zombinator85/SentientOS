from __future__ import annotations

import datetime as _dt
import inspect
import json
import math
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import memory_manager as mm
from resident_kernel import ResidentKernel

_ALLOWED_MEMORY_TAGS = {
    "gesture",
    "tts",
    "presence_pulse",
    "presence",
    "motion",
    "audio",
    "camera",
    "screen",
    "haptics",
    "speech",
}

_NON_WRITABLE_PHASES = {"shutdown"}


def _digest_root() -> Path:
    root = mm.DIGEST_DIR / "embodiment"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _epoch_digest_path(date: _dt.date, epoch_id: int) -> Path:
    return _digest_root() / f"{date.isoformat()}_epoch-{epoch_id}.jsonl"


def _parse_timestamp(value: str | None) -> _dt.datetime:
    if not value:
        return _dt.datetime.utcnow()
    try:
        return _dt.datetime.fromisoformat(value)
    except Exception:
        return _dt.datetime.utcnow()


def _kernel_is_writable(kernel: ResidentKernel) -> bool:
    view = kernel.governance_view()
    if view.system_phase in _NON_WRITABLE_PHASES:
        return False
    return kernel.epoch_active()


def _called_from_plugin_framework() -> bool:
    for frame in inspect.stack()[1:8]:
        module = inspect.getmodule(frame.frame)
        if module and module.__name__ == "plugin_framework" and frame.function == "run_plugin":
            return True
    return False


def _safe_value(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return None


def sanitize_action_summary(event: Mapping[str, object] | None) -> dict[str, object]:
    if not event:
        return {}
    if "type" in event and "value" in event:
        action_type = event.get("type")
        if isinstance(action_type, str) and action_type.strip():
            return {
                "type": action_type,
                "value": _safe_value(event.get("value")),
            }
    if "gesture" in event:
        return {"type": "gesture", "value": _safe_value(event.get("gesture"))}
    if "action" in event:
        return {"type": "action", "value": _safe_value(event.get("action"))}
    if "signal_type" in event:
        return {"type": "signal_type", "value": _safe_value(event.get("signal_type"))}
    if "name" in event:
        return {"type": "name", "value": _safe_value(event.get("name"))}
    return {}


def filter_memory_tags(tags: Iterable[str] | None) -> list[str]:
    if not tags:
        return []
    allowed: list[str] = []
    for tag in tags:
        if not isinstance(tag, str):
            continue
        normalized = tag.strip()
        if normalized and normalized in _ALLOWED_MEMORY_TAGS:
            allowed.append(normalized)
    return allowed


def record_embodiment_digest_entry(
    *,
    kernel: ResidentKernel,
    plugin_name: str,
    declared_capability: Sequence[str],
    posture: str,
    epoch_id: int | None,
    action_summary: Mapping[str, object],
    memory_tags: Sequence[str] | None = None,
    timestamp: str | None = None,
    dry_run: bool = False,
) -> bool:
    if not _called_from_plugin_framework():
        return False
    if dry_run:
        return False
    if epoch_id is None or not kernel.epoch_active():
        return False
    if kernel.active_epoch_id() != epoch_id:
        return False
    if not _kernel_is_writable(kernel):
        return False
    entry_ts = timestamp or _dt.datetime.utcnow().isoformat()
    date = _parse_timestamp(entry_ts).date()
    digest_path = _epoch_digest_path(date, epoch_id)
    payload = {
        "timestamp": entry_ts,
        "posture": posture,
        "plugin": plugin_name,
        "declared_capability": list(declared_capability),
        "action": dict(action_summary),
        "epoch_id": epoch_id,
    }
    tags = filter_memory_tags(memory_tags)
    if tags:
        payload["memory_tags"] = tags
    with open(digest_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return True


def _iter_entries_for_date(date: _dt.date) -> list[dict]:
    entries: list[dict] = []
    for path in sorted(_digest_root().glob(f"{date.isoformat()}_epoch-*.jsonl")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def assemble_daily_embodiment_digest(date: _dt.date | None = None) -> list[dict]:
    target_date = date or _dt.datetime.utcnow().date()
    entries = _iter_entries_for_date(target_date)
    if not entries:
        return []
    payload = json.dumps(entries, ensure_ascii=False)
    mm.append_memory(
        payload,
        tags=["embodiment_day_digest"],
        source="embodiment_digest",
        meta={"date": target_date.isoformat(), "count": len(entries)},
    )
    return entries


def get_recent_embodiment_digest(
    n: int | float = 5, *, tags: Sequence[str] | None = None
) -> list[dict]:
    if n <= 0 and not math.isinf(n):
        return []
    allowed_filters = set(filter_memory_tags(tags)) if tags else set()
    entries: list[dict] = []
    for path in sorted(_digest_root().glob("*_epoch-*.jsonl")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if allowed_filters:
                entry_tags = entry.get("memory_tags", [])
                if not any(tag in entry_tags for tag in allowed_filters):
                    continue
            entries.append(entry)
    entries.sort(key=lambda item: str(item.get("timestamp", "")))
    if math.isinf(n):
        return entries
    return entries[-int(n):]
