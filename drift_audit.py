from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, MutableMapping, Sequence

import capability_ledger
from logging_config import get_log_path
import memory_governor
import unified_memory_indexer


@dataclass(frozen=True)
class GrowthSnapshot:
    name: str
    classification: str
    growth: str
    bytes: int
    entries: int | None
    path: str


_DEFAULT_LOG_PATHS: Dict[str, Path] = {
    "relay": get_log_path("relay.log", "SENTIENTOS_RELAY_LOG"),
    "invariant": get_log_path("invariant.log", "SENTIENTOS_INVARIANT_LOG"),
    "autonomy": get_log_path("autonomy.log", "SENTIENTOS_AUTONOMY_LOG"),
    "mesh": get_log_path("mesh.log", "SENTIENTOS_MESH_LOG"),
}


def _path_stats(path: Path) -> tuple[int, int]:
    if not path.exists():
        return (0, 0)
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            lines = sum(1 for _ in handle)
    except OSError:
        lines = 0
    return (size, lines)


def ledger_snapshot(path: Path | None = None) -> GrowthSnapshot:
    target = Path(path) if path else capability_ledger.default_path()
    size, lines = _path_stats(target)
    return GrowthSnapshot(
        name="capability_ledger",
        classification="audit-only",
        growth="append-only",
        bytes=size,
        entries=lines if lines else None,
        path=str(target),
    )


def log_volume_snapshot(
    *,
    log_paths: Mapping[str, Path] | None = None,
    include: Sequence[str] | None = None,
) -> Dict[str, GrowthSnapshot]:
    resolved: MutableMapping[str, Path] = dict(_DEFAULT_LOG_PATHS)
    if log_paths:
        resolved.update({k: Path(v) for k, v in log_paths.items()})
    selected = include if include is not None else resolved.keys()
    snapshots: Dict[str, GrowthSnapshot] = {}
    for key in selected:
        path = resolved.get(key)
        if path is None:
            continue
        size, lines = _path_stats(path)
        snapshots[key] = GrowthSnapshot(
            name=f"log:{key}",
            classification="operational",
            growth="append-only",
            bytes=size,
            entries=lines if lines else None,
            path=str(path),
        )
    return snapshots


def reflection_snapshot() -> GrowthSnapshot:
    summary = memory_governor.metrics(limit=50)
    reflections = 0
    last = summary.get("last_reflection")
    if isinstance(last, Mapping):
        reflections = int(last.get("reflections") or 0)
    return GrowthSnapshot(
        name="reflection_outputs",
        classification="audit-only",
        growth="bounded",
        bytes=reflections,
        entries=reflections,
        path="memory_governor:_LAST_REFLECTION",
    )


def memory_index_snapshot(path: Path | None = None) -> GrowthSnapshot:
    index_path = Path(path) if path else Path(unified_memory_indexer.INDEX_PATH)
    size, lines = _path_stats(index_path)
    entries = 0
    if index_path.exists():
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                entries = len(payload)
        except (OSError, json.JSONDecodeError):
            entries = 0
    return GrowthSnapshot(
        name="unified_memory_index",
        classification="operational",
        growth="rebuilt",
        bytes=size,
        entries=entries if entries else lines or None,
        path=str(index_path),
    )


def snapshot(
    *,
    log_paths: Mapping[str, Path] | None = None,
    include_logs: Sequence[str] | None = None,
    ledger_path: Path | None = None,
    index_path: Path | None = None,
) -> Dict[str, GrowthSnapshot]:
    out = {
        "capability_ledger": ledger_snapshot(path=ledger_path),
        "reflection_outputs": reflection_snapshot(),
        "unified_memory_index": memory_index_snapshot(path=index_path),
    }
    out.update(log_volume_snapshot(log_paths=log_paths, include=include_logs))
    return out


def main() -> None:  # pragma: no cover - CLI
    data = snapshot()
    print(
        json.dumps({k: vars(v) for k, v in data.items()}, indent=2, sort_keys=True)
    )


if __name__ == "__main__":  # pragma: no cover
    main()
