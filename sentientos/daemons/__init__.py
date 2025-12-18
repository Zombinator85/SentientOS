"""Utility daemons and shared infrastructure for SentientOS."""

from __future__ import annotations

import importlib
from types import ModuleType

__all__ = [
    "pulse_bus",
    "pulse_federation",
    "monitoring_daemon",
    "driver_manager",
    "hungry_eyes",
    "reflex_guard",
    "chronos_daemon",
]


def __getattr__(name: str) -> ModuleType:
    if name in __all__:
        return importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(name)


def __dir__() -> list[str]:  # pragma: no cover - convenience only
    return sorted(__all__)
