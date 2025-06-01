import os
import sys
import getpass
import presence_ledger as pl

ADMIN_BANNER = (
    "Sanctuary Privilege • SentientOS runs with full Administrator rights to safeguard memory and doctrine.\n"
    "If you see errors or locked files, please relaunch with Admin privileges."
)

FAIL_MESSAGE = (
    "Ritual refusal: Please run as Administrator to access the cathedral\u2019s memory."
)


def is_admin() -> bool:
    """Return True if running with administrative privileges."""
    if os.name == 'nt':
        try:
            import ctypes  # type: ignore
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    else:
        return os.geteuid() == 0


def require_admin() -> None:
    """Ensure the process is running with admin rights, relaunching if needed."""
    user = getpass.getuser()
    if is_admin():
        print("\U0001F6E1\uFE0F Sanctuary Privilege Check: PASSED")
        print(ADMIN_BANNER)
        pl.log(user, "admin_privilege_check", "success")
        return

    print("\U0001F6E1\uFE0F Sanctuary Privilege Check: FAILED")

    if os.name == 'nt':
        try:
            import ctypes  # type: ignore
            pl.log(user, "admin_privilege_check", "escalated")
            ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                sys.executable,
                " ".join(sys.argv),
                None,
                1,
            )
            sys.exit()
        except Exception:
            pl.log(user, "admin_privilege_check", "failed")
            sys.exit(FAIL_MESSAGE)
    else:
        pl.log(user, "admin_privilege_check", "failed")
        sys.exit(FAIL_MESSAGE)

