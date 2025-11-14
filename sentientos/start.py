"""Unified startup entrypoint for SentientOS runtime shell."""

from __future__ import annotations

import logging
import signal
import threading
from pathlib import Path
from typing import Dict, Optional

from .dashboard.console import ConsoleDashboard, LogBuffer
from .dashboard.status_source import make_log_stream_source, make_status_source
from .runtime.shell import RuntimeShell, load_or_init_config

_RUNTIME_CONFIG_PATH = Path("C:/SentientOS/sentientos_data/config/runtime.json")


def load_config() -> Dict[str, object]:
    """Load runtime configuration, injecting defaults on first run."""

    return load_or_init_config(_RUNTIME_CONFIG_PATH)


def run() -> int:
    """Boot SentientOS runtime shell and block until termination."""

    config = load_config()
    shell = RuntimeShell(config)
    stop_event = threading.Event()
    dashboard_thread: Optional[threading.Thread] = None
    dashboard: Optional[ConsoleDashboard] = None
    persona_handler: Optional[logging.Handler] = None
    dashboard_refresh = 2.0

    def _signal_handler(_signum: int, _frame: object | None) -> None:
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _signal_handler)
        except (ValueError, AttributeError):  # pragma: no cover - platform dependent
            continue

    shell.start()
    interval = max(1.0, float(config["runtime"].get("watchdog_interval", 5.0)) / 2.0)

    dashboard_config = config.get("dashboard")
    if isinstance(dashboard_config, dict) and dashboard_config.get("enabled", False):
        dashboard_refresh = max(0.5, float(dashboard_config.get("refresh_interval_seconds", 2.0)))
        log_buffer = LogBuffer()

        def _persona_state() -> Optional[object]:
            loop = getattr(shell, "_persona_loop", None)
            return getattr(loop, "state", None)

        status_source = make_status_source(
            config=config,
            shell=shell,
            persona_state_getter=_persona_state,
        )
        log_source = make_log_stream_source(log_buffer)
        dashboard = ConsoleDashboard(
            status_source,
            log_stream_source=log_source,
            refresh_interval=dashboard_refresh,
            log_buffer=log_buffer,
        )

        class _DashboardLogHandler(logging.Handler):
            def __init__(self, buffer: LogBuffer) -> None:
                super().__init__(level=logging.INFO)
                self._buffer = buffer

            def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - logging hook
                try:
                    message = self.format(record)
                except Exception:
                    message = record.getMessage()
                self._buffer.add(message)

        persona_handler = _DashboardLogHandler(log_buffer)
        persona_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logging.getLogger("sentientos.persona").addHandler(persona_handler)

        dashboard_thread = threading.Thread(
            target=dashboard.run_loop,
            name="SentientOSDashboard",
            daemon=True,
        )
        dashboard_thread.start()

    try:
        while not stop_event.wait(interval):
            pass
    finally:
        if dashboard:
            dashboard.stop()
        if dashboard_thread:
            dashboard_thread.join(timeout=dashboard_refresh)
        if persona_handler:
            logging.getLogger("sentientos.persona").removeHandler(persona_handler)
        shell.shutdown()
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    raise SystemExit(main())
