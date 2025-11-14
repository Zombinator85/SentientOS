"""Unified startup entrypoint for SentientOS runtime shell."""

from __future__ import annotations

import argparse
import logging
import signal
import threading
from pathlib import Path
from typing import Dict, Optional, Tuple

from .dashboard.console import ConsoleDashboard, LogBuffer
from .dashboard.status_source import make_log_stream_source, make_status_source
from .runtime.bootstrap import (
    ensure_default_config,
    ensure_runtime_dirs,
    get_base_dir,
    validate_model_paths,
)
from .runtime.shell import RuntimeShell, load_or_init_config


LOGGER = logging.getLogger("sentientos.start")


def _bootstrap_runtime() -> Tuple[Dict[str, object], Path, Dict[str, Path], list[str]]:
    base_dir = get_base_dir()
    runtime_dirs = ensure_runtime_dirs(base_dir)
    for name, path in runtime_dirs.items():
        LOGGER.info("Runtime directory ready: %s -> %s", name, path)
    config_path = ensure_default_config(runtime_dirs["config"])
    config = load_or_init_config(config_path)
    warnings = validate_model_paths(config, runtime_dirs["base"])
    return config, config_path, runtime_dirs, warnings


def _print_init_summary(base_dir: Path, config_path: Path, warnings: list[str]) -> None:
    print("SentientOS bootstrap complete.")
    print(f"Base directory: {base_dir}")
    print(f"Config file: {config_path}")
    if warnings:
        print("Warnings detected:")
        for message in warnings:
            print(f"  - {message}")
    else:
        print("Model paths validated successfully.")


def run(init_only: bool = False) -> int:
    """Boot SentientOS runtime shell and block until termination."""

    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO)

    config, config_path, runtime_dirs, warnings = _bootstrap_runtime()
    LOGGER.info("Configuration loaded from %s", config_path)
    for warning in warnings:
        LOGGER.warning(warning)

    if init_only:
        _print_init_summary(runtime_dirs["base"], config_path, warnings)
        return 0

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
    parser = argparse.ArgumentParser(description="Start the SentientOS runtime shell")
    parser.add_argument(
        "--init-only",
        action="store_true",
        help="Perform bootstrap tasks and exit without launching services.",
    )
    args = parser.parse_args()
    return run(init_only=args.init_only)


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    raise SystemExit(main())
