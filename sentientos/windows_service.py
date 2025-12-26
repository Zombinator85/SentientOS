from __future__ import annotations

"""Windows service wrapper for the SentientOS daemon."""

import logging
import sys
from importlib import import_module
from pathlib import Path

from .optional_deps import dependency_available

if dependency_available("pywin32"):
    win32serviceutil = import_module("win32serviceutil")
    win32service = import_module("win32service")
    win32event = import_module("win32event")
else:  # pragma: no cover - Windows only
    win32serviceutil = None
    win32service = None
    win32event = None


LOGGER = logging.getLogger(__name__)


if win32serviceutil is not None:

    class SentientOSService(win32serviceutil.ServiceFramework):  # type: ignore[misc]
        _svc_name_ = "SentientOSDaemon"
        _svc_display_name_ = "SentientOS Local Runtime"

        def __init__(self, args):  # type: ignore[override]
            win32serviceutil.ServiceFramework.__init__(self, args)
            self.stop_event = win32event.CreateEvent(None, 0, 0, None)

        def SvcStop(self):  # type: ignore[N802]
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self.stop_event)

        def SvcDoRun(self):  # type: ignore[N802]
            import subprocess

            script = Path(__file__).resolve().parent.parent / "sentientosd.py"
            LOGGER.info("Starting SentientOS daemon service: %s", script)
            process = subprocess.Popen([sys.executable, str(script)])
            win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)
            LOGGER.info("Stopping SentientOS daemon service")
            process.terminate()

else:

    class SentientOSService:  # type: ignore[too-many-ancestors]
        """Placeholder exposed when pywin32 is not available."""

        _svc_name_ = "SentientOSDaemon"
        _svc_display_name_ = "SentientOS Local Runtime"

        def __init__(self, *args, **kwargs):  # pragma: no cover - placeholder
            raise RuntimeError("pywin32 is required to run SentientOS as a Windows service")


def install_service():
    if win32serviceutil is None:
        raise RuntimeError("pywin32 is required to install the Windows service")
    win32serviceutil.InstallService(
        SentientOSService,
        SentientOSService._svc_name_,
        SentientOSService._svc_display_name_,
    )


def remove_service():
    if win32serviceutil is None:
        raise RuntimeError("pywin32 is required to remove the Windows service")
    win32serviceutil.RemoveService(SentientOSService._svc_name_)


if __name__ == "__main__":
    if win32serviceutil is None:
        raise SystemExit("pywin32 is required to manage the Windows service")
    win32serviceutil.HandleCommandLine(SentientOSService)
