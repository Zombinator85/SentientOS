from __future__ import annotations

"""Windows service wrapper for the SentientOS daemon."""

import logging
import sys
from importlib import import_module
from pathlib import Path
from typing import Any

from .optional_deps import dependency_available

win32serviceutil: Any = None
win32service: Any = None
win32event: Any = None

if dependency_available("pywin32"):
    win32serviceutil = import_module("win32serviceutil")
    win32service = import_module("win32service")
    win32event = import_module("win32event")


LOGGER = logging.getLogger(__name__)


def _service_init(instance: Any, args: object = None) -> None:
    if win32serviceutil is None or win32event is None:
        raise RuntimeError("pywin32 is required to run SentientOS as a Windows service")
    win32serviceutil.ServiceFramework.__init__(instance, args)
    instance.stop_event = win32event.CreateEvent(None, 0, 0, None)


def _service_stop(instance: Any) -> None:
    if win32service is None or win32event is None:
        raise RuntimeError("pywin32 is required to stop the Windows service")
    instance.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
    win32event.SetEvent(instance.stop_event)


def _service_run(instance: Any) -> None:
    if win32event is None:
        raise RuntimeError("pywin32 is required to run SentientOS as a Windows service")
    import subprocess

    script = Path(__file__).resolve().parent.parent / "sentientosd.py"
    LOGGER.info("Starting SentientOS daemon service: %s", script)
    process = subprocess.Popen([sys.executable, str(script)])
    win32event.WaitForSingleObject(instance.stop_event, win32event.INFINITE)
    LOGGER.info("Stopping SentientOS daemon service")
    process.terminate()


_SERVICE_BASE = (
    getattr(win32serviceutil, "ServiceFramework", object)
    if win32serviceutil is not None
    else object
)
SentientOSService: type[Any] = type(
    "SentientOSService",
    (_SERVICE_BASE,),
    {
        "_svc_name_": "SentientOSDaemon",
        "_svc_display_name_": "SentientOS Local Runtime",
        "__init__": _service_init,
        "SvcStop": _service_stop,
        "SvcDoRun": _service_run,
    },
)


def install_service() -> None:
    if win32serviceutil is None:
        raise RuntimeError("pywin32 is required to install the Windows service")
    win32serviceutil.InstallService(
        SentientOSService,
        SentientOSService._svc_name_,
        SentientOSService._svc_display_name_,
    )


def remove_service() -> None:
    if win32serviceutil is None:
        raise RuntimeError("pywin32 is required to remove the Windows service")
    win32serviceutil.RemoveService(SentientOSService._svc_name_)


if __name__ == "__main__":
    if win32serviceutil is None:
        raise SystemExit("pywin32 is required to manage the Windows service")
    win32serviceutil.HandleCommandLine(SentientOSService)
