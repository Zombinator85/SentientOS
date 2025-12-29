"""Read-only introspection trace CLI."""
from __future__ import annotations

import argparse
import json
from typing import Sequence

from sentientos.introspection import DEFAULT_LOG_PATH, TraceSpine, load_events
from sentientos.introspection.narrative_views import (
    ensure_view_allowed,
    render_artifact_view,
    render_cycle_context_view,
    render_event_chain,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sentientos trace",
        description="Read-only introspection trace viewer (no state mutation).",
    )
    parser.add_argument("--log-path", type=str, default=DEFAULT_LOG_PATH, help="Override log path.")
    subparsers = parser.add_subparsers(dest="command")

    view = subparsers.add_parser("view", help="Render deterministic narrative views (read-only).")
    view_subparsers = view.add_subparsers(dest="view_type")

    chain = view_subparsers.add_parser("chain", help="Render an ordered event chain (read-only).")
    chain.add_argument("--last", type=int, default=None, help="Show the last N events.")

    artifact = view_subparsers.add_parser("artifact", help="Render events grouped by artifact hash.")
    artifact.add_argument("artifact_hash", type=str, help="Artifact hash to render.")

    cycle = view_subparsers.add_parser("cycle", help="Render context for a cognition cycle.")
    cycle.add_argument("cycle_id", type=str, help="Cognition cycle event_id or snapshot hash.")

    parser.add_argument("--last", type=int, default=None, help="Show the last N events.")
    parser.add_argument("--artifact", type=str, default=None, help="Filter events by artifact hash.")
    parser.add_argument("--phase", type=str, default=None, help="Filter events by phase.")
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

    try:
        ensure_view_allowed()
    except RuntimeError as exc:
        print(str(exc))
        return 1

    events = load_events(args.log_path)
    spine = TraceSpine(events=events)

    if args.command == "view":
        if args.view_type == "chain":
            trace = spine.linear_trace(last=args.last)
            view = render_event_chain(trace)
        elif args.view_type == "artifact":
            view = render_artifact_view(spine, args.artifact_hash)
        elif args.view_type == "cycle":
            view = render_cycle_context_view(spine, args.cycle_id)
        else:
            parser.parse_args(argv)
            return 1
        for line in view.lines:
            print(line)
        return 0

    trace = spine.linear_trace(phase=args.phase, artifact_id=args.artifact, last=args.last)
    if not trace:
        print("No trace events found.")
        return 0

    for event in trace:
        print(_format_event(event))

    return 0


__all__ = ["main"]
