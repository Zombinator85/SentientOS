"""Proof-budget governor for baseline reclamation."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(slots=True)
class BudgetConfig:
    max_iterations: int
    max_fixes_per_iteration: int
    max_files_changed_per_iteration: int
    max_total_files_changed: int

    @classmethod
    def from_env(cls) -> "BudgetConfig":
        return cls(
            max_iterations=_env_int("SENTIENTOS_FORGE_MAX_ITERS", 6),
            max_fixes_per_iteration=_env_int("SENTIENTOS_FORGE_MAX_FIXES_PER_ITER", 3),
            max_files_changed_per_iteration=_env_int("SENTIENTOS_FORGE_MAX_FILES_PER_ITER", 10),
            max_total_files_changed=_env_int("SENTIENTOS_FORGE_MAX_TOTAL_FILES", 30),
        )


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default
