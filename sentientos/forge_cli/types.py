from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import TypedDict


class PrintableJSON(TypedDict, total=False):
    command: str
    status: str


@dataclass(frozen=True)
class TruncateConfig:
    max_chars: int = 2000


def truncate_large_fields(payload: dict[str, object], *, config: TruncateConfig = TruncateConfig()) -> dict[str, object]:
    trimmed: dict[str, object] = {}
    for key, value in payload.items():
        if isinstance(value, str) and len(value) > config.max_chars:
            trimmed[key] = value[: config.max_chars] + "...<truncated>"
            continue
        trimmed[key] = value
    return trimmed


def load_json_dict(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def print_json(payload: dict[str, object], *, indent: int | None = None, sort_keys: bool = True) -> None:
    print(json.dumps(payload, indent=indent, sort_keys=sort_keys))
