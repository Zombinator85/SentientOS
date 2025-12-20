"""Gradient-bearing field contract and enforcement helpers.

This module provides a minimal, deterministic check that detects gradient-like
fields crossing cycle boundaries. It is intentionally lightweight and only
performs structural inspection of mapping keys to keep enforcement cheap and
predictable.
"""

from __future__ import annotations

from typing import Iterable, Mapping, MutableSequence, Sequence


# Small, explicit denylist of gradient-bearing concepts that must not cross
# cycle boundaries or be persisted between runs.
GRADIENT_FIELD_DENYLIST: frozenset[str] = frozenset(
    {
        "reward",
        "rewards",
        "utility",
        "utilities",
        "score",
        "scores",
        "loss",
        "losses",
        "gradient",
        "gradients",
        "delta",
        "preference",
        "preferences",
        "bias",
    }
)


class GradientInvariantViolation(RuntimeError):
    """Raised when gradient-bearing fields are detected at a cycle boundary."""

    def __init__(self, context: str, *, paths: Sequence[str]) -> None:
        message = "NO_GRADIENT_INVARIANT violated"
        if context:
            message = f"{message} at {context}"
        if paths:
            joined = ", ".join(paths)
            message = f"{message}: gradient-bearing fields detected at {joined}"
        super().__init__(message)
        self.context = context
        self.paths = list(paths)


def _walk(obj: object, path: Sequence[str], found: MutableSequence[str]) -> None:
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            key_str = str(key)
            if key_str.lower() in GRADIENT_FIELD_DENYLIST:
                found.append(" -> ".join([*path, key_str]))
            _walk(value, [*path, key_str], found)
        return
    if isinstance(obj, (list, tuple, set, frozenset)):
        for idx, value in enumerate(obj):
            _walk(value, [*path, str(idx)], found)


def enforce_no_gradient_fields(payload: object, *, context: str) -> None:
    """Ensure ``payload`` does not contain gradient-bearing fields.

    The check inspects mapping keys recursively; it is deterministic and avoids
    mutating the payload. A ``GradientInvariantViolation`` is raised when the
    denylist is encountered so callers fail closed at cycle boundaries.
    """

    found: list[str] = []
    _walk(payload, [], found)
    if found:
        raise GradientInvariantViolation(context, paths=found)


__all__: Iterable[str] = [
    "GradientInvariantViolation",
    "GRADIENT_FIELD_DENYLIST",
    "enforce_no_gradient_fields",
]
