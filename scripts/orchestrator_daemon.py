from __future__ import annotations

import argparse
import signal
import time
from pathlib import Path

from sentientos.orchestrator import OrchestratorConfig, tick

_SHUTDOWN = False


def _handle_sigint(_signum: int, _frame: object) -> None:
    global _SHUTDOWN
    _SHUTDOWN = True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run orchestrator governance ticks.")
    parser.add_argument("--once", action="store_true", help="Run one tick and exit")
    parser.add_argument("--interval", type=int, default=None, help="Override interval seconds")
    args = parser.parse_args(argv)

    signal.signal(signal.SIGINT, _handle_sigint)

    cfg = OrchestratorConfig.from_env()
    interval = max(5, args.interval if args.interval is not None else cfg.interval_seconds)

    while not _SHUTDOWN:
        tick(Path.cwd(), config=cfg, daemon_active=True)
        if args.once:
            break
        time.sleep(interval)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
