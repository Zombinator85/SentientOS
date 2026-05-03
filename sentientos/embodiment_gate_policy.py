from __future__ import annotations

import os
from typing import Any

EMBODIMENT_GATE_ENV_VAR = "EMBODIMENT_INGRESS_GATE_MODE"
PROPOSAL_ONLY_MODE = "proposal_only"
COMPATIBILITY_LEGACY_MODE = "compatibility_legacy"
DISABLED_MODE = "disabled"
_ALLOWED = {PROPOSAL_ONLY_MODE, COMPATIBILITY_LEGACY_MODE, DISABLED_MODE}


def normalize_embodiment_gate_mode(mode: str | None, *, fallback: str = COMPATIBILITY_LEGACY_MODE) -> str:
    candidate = (mode or "").strip().lower()
    if candidate in _ALLOWED:
        return candidate
    normalized_fallback = (fallback or COMPATIBILITY_LEGACY_MODE).strip().lower()
    return normalized_fallback if normalized_fallback in _ALLOWED else COMPATIBILITY_LEGACY_MODE


def resolve_embodiment_gate_mode(
    explicit_mode: str | None = None,
    *,
    env_var: str = EMBODIMENT_GATE_ENV_VAR,
    default_mode: str = COMPATIBILITY_LEGACY_MODE,
) -> str:
    if explicit_mode is not None:
        return normalize_embodiment_gate_mode(explicit_mode, fallback=default_mode)
    env_value = os.getenv(env_var)
    if env_value is not None:
        return normalize_embodiment_gate_mode(env_value, fallback=default_mode)
    return normalize_embodiment_gate_mode(default_mode, fallback=COMPATIBILITY_LEGACY_MODE)


def is_proposal_only_mode(mode: str | None) -> bool:
    return normalize_embodiment_gate_mode(mode) == PROPOSAL_ONLY_MODE


def is_compatibility_legacy_mode(mode: str | None) -> bool:
    return normalize_embodiment_gate_mode(mode) == COMPATIBILITY_LEGACY_MODE


def gate_mode_receipt_fields(mode: str | None) -> dict[str, Any]:
    normalized = normalize_embodiment_gate_mode(mode)
    return {
        "ingress_gate_mode": normalized,
        "transition_state": "legacy_fallback" if normalized == COMPATIBILITY_LEGACY_MODE else "proposal_only",
        "legacy_direct_effect_preserved": normalized == COMPATIBILITY_LEGACY_MODE,
        "decision_power": "none",
        "non_authoritative": True,
    }


__all__ = [
    "EMBODIMENT_GATE_ENV_VAR",
    "PROPOSAL_ONLY_MODE",
    "COMPATIBILITY_LEGACY_MODE",
    "DISABLED_MODE",
    "normalize_embodiment_gate_mode",
    "resolve_embodiment_gate_mode",
    "is_proposal_only_mode",
    "is_compatibility_legacy_mode",
    "gate_mode_receipt_fields",
]
