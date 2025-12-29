"""Read-only introspection trace CLI."""
from __future__ import annotations

import argparse
import json
from typing import Sequence

from sentientos.introspection import DEFAULT_LOG_PATH, TraceSpine, load_events


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sentientos trace", description="Trace introspection spine events")
    parser.add_argument("--last", type=int, default=None, help="Show the last N events.")
    parser.add_argument("--artifact", type=str, default=None, help="Filter events by artifact hash.")
    parser.add_argument("--phase", type=str, default=None, help="Filter events by phase.")
    parser.add_argument("--log-path", type=str, default=DEFAULT_LOG_PATH, help="Override log path.")
    return parser


def _format_event(event) -> str:
    metadata = json.dumps(event.metadata, sort_keys=True)
    artifacts = ",".join(event.linked_artifact_ids) if event.linked_artifact_ids else "-"
    return (
        f"{event.timestamp_logical:06d} | {event.event_type.value} | phase={event.phase} | "
        f"{event.summary} | artifacts={artifacts} | metadata={metadata}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    events = load_events(args.log_path)
    spine = TraceSpine(events=events)
    trace = spine.linear_trace(phase=args.phase, artifact_id=args.artifact, last=args.last)

    if not trace:
        print("No trace events found.")
        return 0

    for event in trace:
        print(_format_event(event))

    return 0


__all__ = ["main"]
