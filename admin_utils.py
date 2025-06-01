import os
import sys
import presence_ledger as pl

ADMIN_BANNER = (
    "Sanctuary: SentientOS runs as Administrator to protect memory, logs, and presence.\n"
    "If you see errors or locked files, please relaunch with Admin privileges."
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
    if is_admin():
        print(ADMIN_BANNER)
        pl.log('system', 'admin_privilege_check', 'success')
        return

    if os.name == 'nt':
        try:
            import ctypes  # type: ignore
            pl.log('system', 'admin_privilege_check', 'escalated')
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
            pl.log('system', 'admin_privilege_check', 'failed')
            sys.exit('Administrator privileges required')
    else:
        pl.log('system', 'admin_privilege_check', 'failed')
        sys.exit('Administrator privileges required')

