from __future__ import annotations

from contextlib import contextmanager


class RecursionLimitExceeded(RuntimeError):
    """Raised when the recursion guard depth exceeds the configured maximum."""


class RecursionGuard:
    """Depth-limited recursion guard with deterministic bookkeeping.

    The guard is intentionally side-effect-free: it only tracks depth in memory
    for the lifetime of the instance. No scheduling, timers, or external state
    are touched.
    """

    def __init__(self, max_depth: int = 7) -> None:
        self.max_depth = max_depth
        self._depth = 0

    @property
    def depth(self) -> int:
        """Current depth tracked by the guard."""

        return self._depth

    @contextmanager
    def enter(self):
        self._depth += 1
        try:
            if self._depth > self.max_depth:
                raise RecursionLimitExceeded(
                    f"Recursion depth {self._depth} exceeds max {self.max_depth}"
                )
            yield self
        finally:
            self._depth -= 1


__all__ = ["RecursionGuard", "RecursionLimitExceeded"]
