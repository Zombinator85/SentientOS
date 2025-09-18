"""Command line utilities for querying pulse and monitoring data."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Mapping

from sentientos import pulse_query


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect pulse history and monitoring metrics.")
    subparsers = parser.add_subparsers(dest="command")

    query = subparsers.add_parser("query", help="Fetch pulse events and monitoring metrics")
    query.add_argument("--last", default="1h", help="Time window for events, e.g. '24h'.")
    query.add_argument("--since", help="ISO timestamp to start from (overrides --last).")
    query.add_argument(
        "--window",
        help="Monitoring metrics window (defaults to the --last value).",
    )
    query.add_argument("--priority", help="Limit results to a specific priority level.")
    query.add_argument("--daemon", dest="source_daemon", help="Limit by source daemon name.")
    query.add_argument("--event-type", help="Limit by event type.")
    query.add_argument(
        "--samples",
        type=int,
        default=3,
        help="Number of sample events and anomalies to display.",
    )
    query.add_argument(
        "--metrics-only",
        action="store_true",
        help="Only display monitoring metrics (skip event listing).",
    )
    query.add_argument(
        "--events-only",
        action="store_true",
        help="Only display pulse events (skip metrics lookup).",
    )
    query.set_defaults(func=_run_query_command)

    return parser


def _run_query_command(args: argparse.Namespace) -> int:
    filters: Dict[str, str] = {}
    if args.priority:
        filters["priority"] = args.priority
    if args.source_daemon:
        filters["source_daemon"] = args.source_daemon
    if args.event_type:
        filters["event_type"] = args.event_type

    try:
        since = _determine_since(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    metrics_window = args.window or args.last or "1h"
    errors: List[str] = []

    events: List[dict[str, object]] = []
    if not args.metrics_only:
        try:
            events = pulse_query.query_events(since, filters, requester="cli")
        except Exception as exc:  # pragma: no cover - defensive path
            errors.append(f"events query failed: {exc}")

    metrics_result: dict[str, object] | None = None
    if not args.events_only:
        try:
            metrics_result = pulse_query.query_metrics(metrics_window, filters, requester="cli")
        except Exception as exc:  # pragma: no cover - defensive path
            errors.append(f"metrics query failed: {exc}")

    _print_summary(since, metrics_window, filters, events, metrics_result, args.samples)

    if errors:
        for message in errors:
            print(f"warning: {message}", file=sys.stderr)
        return 1
    return 0


def _determine_since(args: argparse.Namespace) -> datetime:
    if args.since:
        return pulse_query.parse_iso_timestamp(args.since)
    window = args.last or "1h"
    delta = pulse_query.parse_window(window)
    return datetime.now(timezone.utc) - delta


def _print_summary(
    since: datetime,
    metrics_window: str,
    filters: Mapping[str, str],
    events: Iterable[Mapping[str, object]],
    metrics: Mapping[str, object] | None,
    samples: int,
) -> None:
    print("Pulse Query Summary")
    print("===================")
    print(f"Since: {since.isoformat()}")
    print(f"Metrics window: {metrics_window}")
    if filters:
        joined = ", ".join(f"{key}={value}" for key, value in filters.items())
        print(f"Filters: {joined}")
    else:
        print("Filters: none")

    event_list = list(events)
    print("\nEvents")
    print("------")
    print(f"Matched events: {len(event_list)}")
    if event_list:
        for event in event_list[: max(samples, 0)]:
            print(f"- {_format_event(event)}")
        remaining = len(event_list) - max(samples, 0)
        if remaining > 0:
            print(f"... {remaining} more")
    else:
        print("No matching events found.")

    print("\nMetrics")
    print("-------")
    if metrics is None:
        print("Metrics lookup skipped.")
        return

    summary = metrics.get("summary") if isinstance(metrics, Mapping) else None
    if isinstance(summary, Mapping):
        total = summary.get("total_events", 0)
        print(f"Total events: {total}")
        rate_min = summary.get("rate_per_minute")
        if isinstance(rate_min, (int, float)):
            print(f"Rate/minute: {rate_min:.2f}")
        rate_hour = summary.get("rate_per_hour")
        if isinstance(rate_hour, (int, float)):
            print(f"Rate/hour: {rate_hour:.2f}")
        _print_counter("By priority", summary.get("priority"))
        _print_counter("By source", summary.get("source_daemon"))
        _print_counter("By event", summary.get("event_type"))
    else:
        print("No metrics summary available.")

    anomalies = metrics.get("anomalies") if isinstance(metrics, Mapping) else None
    if isinstance(anomalies, list) and anomalies:
        print("Anomalies:")
        for anomaly in anomalies[: max(samples, 0)]:
            print(f"- {_format_anomaly(anomaly)}")
        remaining = len(anomalies) - max(samples, 0)
        if remaining > 0:
            print(f"... {remaining} more")
    else:
        print("Anomalies: none")


def _print_counter(title: str, data: object) -> None:
    if not isinstance(data, Mapping) or not data:
        return
    items = ", ".join(f"{key}={data[key]}" for key in sorted(data))
    print(f"{title}: {items}")


def _format_event(event: Mapping[str, object]) -> str:
    timestamp = str(event.get("timestamp", ""))
    priority = str(event.get("priority", "info")).upper()
    daemon = str(event.get("source_daemon", "unknown"))
    event_type = str(event.get("event_type", "unknown"))
    return f"{timestamp} {priority:<8} {daemon} :: {event_type}"


def _format_anomaly(anomaly: Mapping[str, object]) -> str:
    timestamp = str(anomaly.get("timestamp", ""))
    daemon = str(anomaly.get("source_daemon", ""))
    priority = str(anomaly.get("priority", "")).upper()
    observed = anomaly.get("observed", 0)
    threshold = anomaly.get("threshold", 0)
    name = anomaly.get("name", "threshold")
    return (
        f"{timestamp} {daemon} {priority} observed={observed} "
        f"threshold={threshold} name={name}"
    )


def main(argv: List[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 1
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 1
    return int(func(args))


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())

