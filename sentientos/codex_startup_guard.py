from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator


class CodexStartupViolation(RuntimeError):
    """Raised when startup-only Codex governance entrypoints are used at runtime."""

    def __init__(self, symbol: str) -> None:
        super().__init__(
            (
                f"{symbol} is restricted to Codex startup orchestration; "
                "wrap construction in codex_startup_phase() or run during bootstrap."
            )
        )


_STARTUP_ACTIVE = False


def enforce_codex_startup(symbol: str) -> None:
    """Abort startup-only entrypoint construction when bootstrap is not active."""

    if not _STARTUP_ACTIVE:
        raise CodexStartupViolation(symbol)


@contextmanager
def codex_startup_phase() -> Iterator[None]:
    """Temporarily allow Codex startup-only governance entrypoints to be constructed."""

    global _STARTUP_ACTIVE
    previous = _STARTUP_ACTIVE
    _STARTUP_ACTIVE = True
    try:
        yield
    finally:
        _STARTUP_ACTIVE = previous
