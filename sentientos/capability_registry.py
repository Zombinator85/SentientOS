"""In-memory capability registry for session-scoped disablement."""

from __future__ import annotations

import hashlib
import json
from typing import Mapping


_DISABLED_CAPABILITIES: dict[str, str] = {}


def disable_capability(capability: str, *, reason: str) -> bool:
    if capability in _DISABLED_CAPABILITIES:
        return False
    _DISABLED_CAPABILITIES[capability] = reason
    return True


def is_capability_disabled(capability: str) -> bool:
    return capability in _DISABLED_CAPABILITIES


def disabled_capability_reason(capability: str) -> str | None:
    return _DISABLED_CAPABILITIES.get(capability)


def disabled_capabilities() -> Mapping[str, str]:
    return dict(_DISABLED_CAPABILITIES)


def reset_capability_registry() -> None:
    _DISABLED_CAPABILITIES.clear()


def capability_snapshot_hash() -> str:
    payload = json.dumps(
        {"disabled": _DISABLED_CAPABILITIES},
        separators=(",", ":"),
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "disable_capability",
    "is_capability_disabled",
    "disabled_capability_reason",
    "disabled_capabilities",
    "reset_capability_registry",
    "capability_snapshot_hash",
]
