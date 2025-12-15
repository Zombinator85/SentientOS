from __future__ import annotations

"""Privilege helper utilities.

Actions continue with alignment-contract auto-enforcement; no approval prompts
are emitted and unattended runs stay guarded automatically.
"""

import getpass
import os
import sys
import platform
import logging
from typing import TYPE_CHECKING, Any
import warnings

logger = logging.getLogger(__name__)
from pathlib import Path
if TYPE_CHECKING:
    import presence_ledger as pl_module
    import privilege_lint as pl_lint_module


class _StubLedger:
    def log_privilege(self, *a: object, **k: object) -> None:
        pass

    def log(self, *a: object, **k: object) -> None:
        pass
from typing import Any

pl: Any = _StubLedger()

ADMIN_BANNER = (
    "Administrator Privilege • SentientOS is running with elevated rights to safeguard memory and policy state.\n"
    "If you see errors or locked files, please relaunch with Administrator privileges."
)

FAIL_MESSAGE = (
    "Access denied: run as Administrator to reach protected memory and policy state."
)


def _elevation_hint() -> str:
    if os.name == "nt":
        return "How to fix: Right-click the command and choose 'Run as administrator'."
    if sys.platform == "darwin":
        return "How to fix: Prefix the command with 'sudo' or run from an admin account."
    return "How to fix: Run this command with 'sudo'."


def print_privilege_banner(tool: str = "") -> None:
    """Print the current privilege status banner."""
    user = getpass.getuser()
    plat = platform.system()
    status = "\U0001F6E1\uFE0F Privileged" if is_admin() else "\u26A0\uFE0F Not Privileged"
    logger.info("\U0001F6E1\uFE0F Administrator Privilege Status: [%s]", status)
    logger.info("Current user: %s", user)
    logger.info("Platform: %s", plat)
    if not is_admin():
        logger.info(
            "Access denied: administrator rights are required to read protected memory, logs, and policy state."
        )
        logger.info(_elevation_hint())


def is_admin() -> bool:
    """Return True if running with administrative privileges."""
    if os.name == "nt":
        try:
            import ctypes  # windows admin API
            windll = getattr(ctypes, "windll", None)
            if windll is None:
                return False
            return bool(windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    else:
        return os.geteuid() == 0



def require_admin_banner() -> None:
    """Display the privilege banner and enforce administrator rights."""

    user = getpass.getuser()
    tool = Path(sys.argv[0]).stem
    print_privilege_banner(tool)
    global pl
    if (
        isinstance(pl, _StubLedger)
        and pl.__class__ is _StubLedger
        and pl.log_privilege == _StubLedger.log_privilege
    ):
        import presence_ledger as pl_module

        pl = pl_module
    _log_privilege = pl.log_privilege
    try:
        import privilege_lint as pl_lint

        pl_lint.audit_use("cli", tool)  # type: ignore[attr-defined]  # runtime plugin may lack stubs
    except Exception:
        pass
    if is_admin():
        _log_privilege(user, platform.system(), tool, "success")
        logger.info(ADMIN_BANNER)
        return

    if os.name == "nt":
        try:
            import ctypes  # windows admin API

            windll = getattr(ctypes, "windll", None)
            if windll is None:
                raise RuntimeError("No windll")
            _log_privilege(user, platform.system(), tool, "escalated")
            windll.shell32.ShellExecuteW(
                None,
                "runas",
                sys.executable,
                " ".join(sys.argv),
                None,
                1,
            )
            sys.exit()
        except Exception:
            _log_privilege(user, platform.system(), tool, "failed")
            sys.exit(FAIL_MESSAGE)
    else:
        _log_privilege(user, platform.system(), tool, "failed")
        sys.exit(FAIL_MESSAGE)


def require_covenant_alignment() -> None:
    """Ensure alignment-contract guardrails are engaged without user prompts."""

    global pl
    if (
        isinstance(pl, _StubLedger)
        and pl.__class__ is _StubLedger
        and pl.log_privilege == _StubLedger.log_privilege
    ):
        import presence_ledger as pl_module

        pl = pl_module

    from sentientos.integrity import covenant_autoalign

    covenant_autoalign.autoalign_on_boot()
    pl.log("system", "covenant_autoalign", Path(sys.argv[0]).stem)


def require_admin() -> None:
    """Deprecated. Use :func:`require_covenant_alignment` instead."""

    warnings.warn(
        "require_admin() is deprecated; use require_covenant_alignment()",
        DeprecationWarning,
        stacklevel=2,
    )
    require_covenant_alignment()


def require_lumos_approval() -> None:
    """Deprecated alias for covenant auto-alignment."""

    warnings.warn(
        "require_lumos_approval() is deprecated; use require_covenant_alignment()",
        DeprecationWarning,
        stacklevel=2,
    )
    require_covenant_alignment()


__all__ = [
    "is_admin",
    "print_privilege_banner",
    "require_admin_banner",
    "require_covenant_alignment",
    "require_lumos_approval",
    "require_admin",
]

