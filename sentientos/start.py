"""Unified startup entrypoint for SentientOS runtime shell."""

from __future__ import annotations

import argparse
import logging
import signal
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from .dashboard.console import ConsoleDashboard, LogBuffer
from .dashboard.status_source import make_log_stream_source, make_status_source
from .experiments import demo_gallery
from .runtime.bootstrap import (
    ensure_default_config,
    ensure_runtime_dirs,
    get_base_dir,
    validate_model_paths,
)
from .runtime.shell import RuntimeShell, load_or_init_config


LOGGER = logging.getLogger("sentientos.start")


def _run_world_demo(
    name: str,
    buffer: LogBuffer,
    speak_callback: Optional[Callable[[str], None]] = None,
) -> None:
    buffer.add(f"World event triggered demo '{name}' starting.")
    if speak_callback:
        try:
            speak_callback(f"Demo {name} starting")
        except Exception:  # pragma: no cover - defensive logging
            LOGGER.exception("World demo speak callback failed (start)")
    try:
        result = demo_gallery.run_demo(name, stream=lambda line: buffer.add(str(line)))
    except Exception as exc:  # pragma: no cover - defensive logging
        buffer.add(f"Demo '{name}' failed: {exc}")
        if speak_callback:
            try:
                speak_callback(f"Demo {name} failed")
            except Exception:  # pragma: no cover - defensive logging
                LOGGER.exception("World demo speak callback failed (error)")
        return

    outcome = getattr(getattr(result, "result", None), "outcome", "").lower()
    if outcome == "success":
        buffer.add(f"Demo '{name}' completed successfully.")
        if speak_callback:
            try:
                speak_callback(f"Demo {name} completed successfully")
            except Exception:  # pragma: no cover - defensive logging
                LOGGER.exception("World demo speak callback failed (success)")
    else:
        outcome_text = outcome or "unknown"
        buffer.add(f"Demo '{name}' completed with outcome: {outcome_text}")
        if speak_callback:
            try:
                speak_callback(f"Demo {name} completed with outcome {outcome_text}")
            except Exception:  # pragma: no cover - defensive logging
                LOGGER.exception("World demo speak callback failed (outcome)")


def load_config() -> Dict[str, object]:
    """Return the runtime configuration, creating defaults if needed."""

    base_dir = get_base_dir()
    runtime_dirs = ensure_runtime_dirs(base_dir)
    config_path = ensure_default_config(runtime_dirs["config"])
    return load_or_init_config(config_path)


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
    world_demo_thread: Optional[threading.Thread] = None
    world_demo_stop = threading.Event()
    world_demo_poll_interval = 1.0
    dashboard_refresh = 2.0
    log_buffer: Optional[LogBuffer] = None

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
        shell.register_dashboard_notifier(log_buffer.add)

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

    world_config = config.get("world")
    if (
        isinstance(world_config, dict)
        and world_config.get("enabled", True)
        and log_buffer is not None
    ):
        demo_cfg = world_config.get("demo_trigger")
        bus = shell.world_bus
        if (
            isinstance(demo_cfg, dict)
            and demo_cfg.get("enabled")
            and bus is not None
        ):
            demo_name = str(demo_cfg.get("demo_name") or "demo_simple_success").strip() or "demo_simple_success"
            try:
                poll_interval = float(world_config.get("poll_interval_seconds", 2.0))
            except (TypeError, ValueError):
                poll_interval = 2.0
            world_demo_poll_interval = max(0.5, poll_interval)
            speak_callback = getattr(shell, "_speak_callback", None)

            def _watch_world_events() -> None:
                last_ts: Optional[datetime] = None
                while not world_demo_stop.is_set():
                    events = bus.drain_since(last_ts)
                    if events:
                        last_ts = events[-1].ts
                        for event in events:
                            if event.kind == "demo_trigger":
                                _run_world_demo(demo_name, log_buffer, speak_callback)
                    if world_demo_stop.wait(world_demo_poll_interval):
                        break

            world_demo_thread = threading.Thread(
                target=_watch_world_events,
                name="WorldDemoTrigger",
                daemon=True,
            )
            world_demo_thread.start()

    try:
        while not stop_event.wait(interval):
            pass
    finally:
        if dashboard:
            dashboard.stop()
        if dashboard_thread:
            dashboard_thread.join(timeout=dashboard_refresh)
        world_demo_stop.set()
        if world_demo_thread:
            world_demo_thread.join(timeout=world_demo_poll_interval)
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
