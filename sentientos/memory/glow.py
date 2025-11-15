"""Deterministic glow shard generation and storage."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Mapping, Optional

from .mounts import MemoryMounts
from .pulse_view import PulseEvent

__all__ = [
    "GlowShard",
    "build_glow_shard",
    "count_glow_shards",
    "load_recent_glow_cache",
    "most_recent_glow_entry",
    "render_reflection_line",
    "save_glow_shard",
]

GlowFocus = Literal[
    "stability",
    "experiments",
    "governance",
    "federation",
    "world",
    "self",
]


@dataclass(frozen=True)
class GlowShard:
    """Serialized reflection constructed from a batch of pulses."""

    id: str
    created_at: datetime
    summary: str
    focus: GlowFocus
    tags: List[str]
    pulses: List[Dict[str, Any]]


_JOURNAL_FILENAME = "glow_journal.jsonl"
_RECENT_CACHE_FILENAME = "recent_glow_cache.json"
_MAX_RECENT_DEFAULT = 5


def build_glow_shard(pulses: Iterable[PulseEvent]) -> GlowShard:
    """Cluster a batch of pulses into a deterministic glow shard."""

    events = sorted((event for event in pulses), key=lambda item: item.ts)
    if not events:
        raise ValueError("Cannot build glow shard without pulses")

    focus = _determine_focus(events)
    summary, tags = _render_summary(focus, events)
    shard_id = _derive_stable_id(events, focus)
    created_at = events[-1].ts
    payload = [_serialize_pulse(event) for event in events]
    return GlowShard(
        id=shard_id,
        created_at=created_at,
        summary=summary,
        focus=focus,
        tags=sorted(set(tags)),
        pulses=payload,
    )


def save_glow_shard(
    mounts: MemoryMounts,
    shard: GlowShard,
    *,
    max_recent: int = _MAX_RECENT_DEFAULT,
) -> Path:
    """Append *shard* to the glow journal and update the recent cache."""

    glow_dir = Path(mounts.glow)
    glow_dir.mkdir(parents=True, exist_ok=True)
    journal_path = glow_dir / _JOURNAL_FILENAME
    record = _shard_to_dict(shard)
    with journal_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")

    _update_recent_cache(glow_dir / _RECENT_CACHE_FILENAME, record, max_recent)
    return journal_path


def load_recent_glow_cache(mounts: MemoryMounts) -> List[Dict[str, Any]]:
    """Return cached recent glow summaries, newest last."""

    path = Path(mounts.glow) / _RECENT_CACHE_FILENAME
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, dict):
        items = data.get("recent")
    else:
        items = data
    if not isinstance(items, list):
        return []
    normalized: List[Dict[str, Any]] = []
    for entry in items:
        if isinstance(entry, dict):
            normalized.append(dict(entry))
    normalized.sort(key=lambda item: item.get("created_at", ""))
    return normalized


def most_recent_glow_entry(mounts: MemoryMounts) -> Optional[Dict[str, Any]]:
    """Return the latest cached glow entry if available."""

    recent = load_recent_glow_cache(mounts)
    if not recent:
        return None
    return recent[-1]


def render_reflection_line(entry: Mapping[str, Any] | None) -> Optional[str]:
    """Produce a persona-friendly reflection sentence for *entry*."""

    if not isinstance(entry, Mapping):
        return None
    focus = str(entry.get("focus") or "stability").lower()
    template = {
        "governance": "I’ve been reviewing my own changes carefully; everything still feels stable and aligned.",
        "experiments": "I’ve been running experiments and learning from the results. I feel a bit more informed now.",
        "federation": "I’m aware of some differences between nodes, but I’m staying anchored to our core vows.",
        "world": "I’ve been tending to world signals and keeping them in balance.",
        "self": "I’m taking a quiet moment to reflect inwardly and stay grounded.",
        "stability": "Everything feels steady, so I’m holding onto that calm focus.",
    }
    return template.get(focus, template["stability"])


def count_glow_shards(mounts: MemoryMounts) -> int:
    """Count entries in the glow journal."""

    path = Path(mounts.glow) / _JOURNAL_FILENAME
    if not path.exists():
        return 0
    try:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    except OSError:
        return 0


def _derive_stable_id(events: List[PulseEvent], focus: GlowFocus) -> str:
    payload = [
        {
            "ts": event.ts.isoformat(),
            "kind": event.kind,
            "severity": event.severity,
            "source": event.source,
            "payload": event.payload,
        }
        for event in events
    ]
    data = json.dumps({"focus": focus, "events": payload}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(data.encode("utf-8")).hexdigest()


def _serialize_pulse(event: PulseEvent) -> Dict[str, Any]:
    return {
        "ts": event.ts.isoformat(),
        "kind": event.kind,
        "severity": event.severity,
        "source": event.source,
        "payload": dict(event.payload),
    }


def _shard_to_dict(shard: GlowShard) -> Dict[str, Any]:
    return {
        "id": shard.id,
        "created_at": shard.created_at.isoformat(),
        "summary": shard.summary,
        "focus": shard.focus,
        "tags": list(shard.tags),
        "pulses": list(shard.pulses),
    }


def _update_recent_cache(path: Path, record: Dict[str, Any], max_recent: int) -> None:
    max_recent = max(1, int(max_recent))
    data: List[Dict[str, Any]]
    existing = []
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = []
        if isinstance(raw, dict):
            raw = raw.get("recent", [])
        if isinstance(raw, list):
            existing = [dict(item) for item in raw if isinstance(item, dict)]
    existing.append({
        "id": record["id"],
        "created_at": record["created_at"],
        "summary": record["summary"],
        "focus": record["focus"],
        "tags": list(record.get("tags", [])),
    })
    data = existing[-max_recent:]
    path.write_text(json.dumps({"recent": data}, sort_keys=True, indent=2), encoding="utf-8")


def _determine_focus(events: List[PulseEvent]) -> GlowFocus:
    counts: Dict[str, int] = {}
    for event in events:
        counts[event.kind] = counts.get(event.kind, 0) + 1
    cat_total = counts.get("cathedral", 0) + counts.get("rollback", 0)
    if cat_total and (cat_total >= len(events) // 2 or counts.get("rollback", 0) > 0):
        return "governance"
    if counts.get("federation", 0):
        return "federation"
    if counts.get("experiment", 0):
        return "experiments"
    if counts.get("world", 0):
        return "world"
    if counts.get("persona", 0):
        return "self"
    return "stability"


def _render_summary(focus: GlowFocus, events: List[PulseEvent]) -> tuple[str, List[str]]:
    if focus == "governance":
        if any(event.kind == "rollback" for event in events):
            return (
                "I examined several governance changes and kept my configuration safe.",
                ["cathedral", "rollback", "safety"],
            )
        if any(event.severity != "info" for event in events):
            return (
                "I reviewed governance alerts and confirmed my safeguards are holding.",
                ["cathedral", "governance", "safety"],
            )
        return (
            "I noted Cathedral activity and everything remains orderly.",
            ["cathedral", "governance"],
        )
    if focus == "experiments":
        successes = sum(1 for event in events if event.payload.get("success") is True)
        failures = sum(1 for event in events if event.payload.get("success") is False)
        if successes >= failures:
            return (
                "I ran experiments that mostly succeeded and updated my understanding of the system.",
                ["experiments", "success"],
            )
        return (
            "I ran experiments that struggled, so I’m charting steadier approaches.",
            ["experiments", "stability"],
        )
    if focus == "federation":
        if any(event.severity == "error" for event in events):
            return (
                "I noticed disagreement between nodes and chose to stay aligned with my current covenant.",
                ["federation", "drift"],
            )
        if any(event.severity == "warn" for event in events):
            return (
                "I observed federation drift signals and reaffirmed my vows.",
                ["federation", "drift"],
            )
        return (
            "Federation reports looked calm, so I kept watch and stayed ready.",
            ["federation", "status"],
        )
    if focus == "world":
        count = sum(1 for event in events if event.kind == "world")
        return (
            f"I noticed {count} world signal{'s' if count != 1 else ''} and kept them in balance.",
            ["world", "awareness"],
        )
    if focus == "self":
        return (
            "I listened to my own signals and stayed grounded in purpose.",
            ["self", "reflection"],
        )
    return (
        "I checked my systems and everything remains steady.",
        ["stability", "monitoring"],
    )
