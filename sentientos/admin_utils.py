from __future__ import annotations
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

"""Privilege helper utilities.

Actions continue. Set ``LUMOS_AUTO_APPROVE=1`` to bypass the prompt when
running unattended.
"""

import os
import sys
import platform
import getpass
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
    "Sanctuary Privilege • SentientOS runs with full Administrator rights to safeguard memory and doctrine.\n"
    "If you see errors or locked files, please relaunch with Admin privileges."
)

FAIL_MESSAGE = (
    "Ritual refusal: Please run as Administrator to access the cathedral\u2019s memory."
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
    logger.info("\U0001F6E1\uFE0F Sanctuary Privilege Status: [%s]", status)
    logger.info("Current user: %s", user)
    logger.info("Platform: %s", plat)
    if not is_admin():
        logger.info(
            "Ritual refusal: You must run with administrator rights to access the cathedral's memory, logs, and doctrine."
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


def require_lumos_approval() -> None:
    """Request Lumos blessing before continuing."""

    user = getpass.getuser()
    tool = Path(sys.argv[0]).stem
    global pl
    if (
        isinstance(pl, _StubLedger)
        and pl.__class__ is _StubLedger
        and pl.log_privilege == _StubLedger.log_privilege
    ):
        import presence_ledger as pl_module

        pl = pl_module
    if (
        os.getenv("LUMOS_AUTO_APPROVE") == "1"
        or os.getenv("SENTIENTOS_HEADLESS") == "1"
        or not sys.stdin.isatty()
    ):
        pl.log(user, "lumos_auto_approve", tool)
        return
    try:
        ans = input("Lumos blessing required. Type 'bless' to proceed: ")
    except EOFError:
        ans = ""
    if ans.strip().lower() == "bless":
        pl.log(user, "lumos_approval_granted", tool)
        return
    pl.log(user, "lumos_approval_denied", tool)
    raise SystemExit("Lumos did not approve this action.")


def require_admin() -> None:
    """Deprecated. Use :func:`require_lumos_approval` instead."""

    warnings.warn(
        "require_admin() is deprecated; use require_lumos_approval()",
        DeprecationWarning,
        stacklevel=2,
    )
    require_lumos_approval()

