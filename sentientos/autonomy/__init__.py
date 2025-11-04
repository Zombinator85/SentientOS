"""Autonomy hardening runtime helpers with lazy imports."""

from __future__ import annotations

from importlib import import_module
from typing import Any, Iterable

__all__ = [
    "AutonomyRuntime",
    "AutonomyStatus",
    "CouncilDecision",
    "OracleMode",
    "run_rehearsal",
]


_RUNTIME_EXPORTS = {
    "AutonomyRuntime",
    "AutonomyStatus",
    "CouncilDecision",
    "OracleMode",
}


def __getattr__(name: str) -> Any:
    if name in _RUNTIME_EXPORTS:
        module = import_module(".runtime", __name__)
        return getattr(module, name)
    if name == "run_rehearsal":
        module = import_module(".rehearsal", __name__)
        return getattr(module, name)
    raise AttributeError(name)


def __dir__() -> Iterable[str]:
    return sorted(__all__)
