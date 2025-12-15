"""Live SentientOS dashboard entrypoint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from sentientos.dashboard.dashboard_snapshot import collect_snapshot
from sentientos.dashboard.live_dashboard import render_snapshot, run_dashboard
from sentientos.pulse.pulse_observer import DEFAULT_PULSE_PATH


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="SentientOS live dashboard")
    parser.add_argument(
        "--refresh-interval",
        type=float,
        default=1.5,
        help="Seconds between dashboard refreshes",
    )
    parser.add_argument(
        "--pulse-path",
        type=Path,
        default=DEFAULT_PULSE_PATH,
        help="Override pulse status path",
    )
    parser.add_argument(
        "--self-path",
        type=Path,
        default=None,
        help="Override self-model path",
    )
    parser.add_argument(
        "--single-frame",
        "--once",
        dest="single_frame",
        action="store_true",
        help="Render a single frame and exit",
    )
    args = parser.parse_args(argv)

    if args.single_frame:
        snapshot = collect_snapshot(pulse_path=args.pulse_path, self_path=args.self_path)
        frame = render_snapshot(snapshot, refresh_interval=args.refresh_interval)
        sys.stdout.write(frame)
        sys.stdout.flush()
        return 0

    run_dashboard(
        refresh_interval=args.refresh_interval,
        pulse_path=args.pulse_path,
        self_path=args.self_path,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    raise SystemExit(main())
