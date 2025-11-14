"""Unified startup entrypoint for SentientOS runtime shell."""

from __future__ import annotations

import signal
import threading
from pathlib import Path
from typing import Dict

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

    def _signal_handler(_signum: int, _frame: object | None) -> None:
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _signal_handler)
        except (ValueError, AttributeError):  # pragma: no cover - platform dependent
            continue

    shell.start()
    interval = max(1.0, float(config["runtime"].get("watchdog_interval", 5.0)) / 2.0)
    try:
        while not stop_event.wait(interval):
            pass
    finally:
        shell.shutdown()
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    raise SystemExit(main())
