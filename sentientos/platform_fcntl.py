"""Import-safe POSIX flock facade for read-only cross-platform recovery.

Windows can import owners whose recovery paths do not need a lock. Any path
that attempts to acquire a POSIX advisory lock fails closed; this module does
not emulate flock with weaker or differently scoped Windows locking.
"""
from __future__ import annotations

import errno

try:  # pragma: no cover - the native branch is exercised on POSIX hosts.
    import fcntl as fcntl
except ImportError:  # pragma: no cover - requires Windows to exercise.
    FLOCK_SUPPORTED = False

    class _UnavailableFcntl:
        LOCK_SH = 1
        LOCK_EX = 2
        LOCK_NB = 4
        LOCK_UN = 8

        @staticmethod
        def flock(_fd: object, _operation: int) -> None:
            raise OSError(errno.ENOSYS, "POSIX flock custody is unavailable")

    fcntl = _UnavailableFcntl()
else:
    FLOCK_SUPPORTED = True


def require_flock() -> None:
    """Refuse effectful work when the native interprocess lock is absent."""
    if not FLOCK_SUPPORTED:
        raise OSError(errno.ENOSYS, "POSIX flock custody is unavailable")

__all__ = ["FLOCK_SUPPORTED", "fcntl", "require_flock"]
