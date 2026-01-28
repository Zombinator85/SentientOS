from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import Iterable, Mapping

_SILHOUETTE_ENV = "SENTIENTOS_SILHOUETTE_DIR"
_DATA_ROOT_ENV = "SENTIENTOS_DATA_DIR"


def _candidate_dirs() -> list[Path]:
    candidates: list[Path] = []
    env_dir = os.environ.get(_SILHOUETTE_ENV)
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.append(Path("glow") / "silhouettes")
    data_root = os.environ.get(_DATA_ROOT_ENV)
    if data_root:
        candidates.append(Path(data_root) / "glow" / "silhouettes")
    else:
        candidates.append(Path.cwd() / "sentientos_data" / "glow" / "silhouettes")
    return candidates


def resolve_silhouette_dir() -> Path:
    for candidate in _candidate_dirs():
        if candidate.exists():
            return candidate
    return _candidate_dirs()[0]


def _iter_silhouette_paths() -> Iterable[Path]:
    base = resolve_silhouette_dir()
    if not base.exists():
        return []
    paths = [path for path in base.glob("*.json") if path.is_file()]
    paths.sort(key=lambda path: path.stem, reverse=True)
    return paths


def _load_payload(path: Path) -> Mapping[str, object] | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, Mapping):
        return payload
    return None


def _with_source(payload: Mapping[str, object]) -> dict[str, object]:
    wrapped = dict(payload)
    wrapped["source"] = "embodiment_silhouette"
    return wrapped


def list_silhouette_dates(limit: int | None = None) -> list[str]:
    dates: list[str] = []
    for path in _iter_silhouette_paths():
        dates.append(path.stem)
        if limit is not None and len(dates) >= limit:
            break
    return dates


def load_silhouette(date_value: str) -> dict[str, object] | None:
    try:
        _dt.date.fromisoformat(date_value)
    except ValueError:
        raise ValueError("silhouette date must be YYYY-MM-DD")
    base = resolve_silhouette_dir()
    path = base / f"{date_value}.json"
    payload = _load_payload(path)
    if payload is None:
        return None
    return _with_source(payload)


def load_recent_silhouettes(n: int = 7) -> list[dict[str, object]]:
    if not isinstance(n, int) or n <= 0:
        return []
    silhouettes: list[dict[str, object]] = []
    for path in _iter_silhouette_paths():
        payload = _load_payload(path)
        if payload is None:
            continue
        silhouettes.append(_with_source(payload))
        if len(silhouettes) >= n:
            break
    return silhouettes
