from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from sentientos.ois import (
    build_execution_trace,
    build_explanation,
    build_simulation,
    build_system_overview,
    log_introspection_access,
    serialize_output,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sentientos ois",
        description="Read-only Operator Introspection Surface (OIS)",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("overview", help="Show system state overview.")

    trace = subparsers.add_parser("trace", help="Show execution trace (read-only).")
    trace.add_argument("--limit", type=int, default=10, help="Maximum number of executions to display.")

    explain = subparsers.add_parser("explain", help="Explain why or why-not outcomes.")
    explain_group = explain.add_mutually_exclusive_group(required=True)
    explain_group.add_argument("--task-id", help="Task ID to explain.")
    explain_group.add_argument("--routine-id", help="Routine ID to explain.")

    simulate = subparsers.add_parser("simulate", help="Dry-run simulation (no side effects).")
    simulate_group = simulate.add_mutually_exclusive_group(required=True)
    simulate_group.add_argument("--task-file", help="Path to task JSON payload.")
    simulate_group.add_argument("--routine-id", help="Routine ID to simulate.")
    simulate_group.add_argument("--adapter", nargs=2, metavar=("ADAPTER_ID", "ACTION"))

    return parser


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "overview":
        log_introspection_access("overview")
        output = build_system_overview()
        print(serialize_output(output))
        return 0

    if args.command == "trace":
        log_introspection_access("trace", detail={"limit": args.limit})
        output = build_execution_trace(limit=args.limit)
        print(serialize_output(output))
        return 0

    if args.command == "explain":
        detail = {"task_id": args.task_id, "routine_id": args.routine_id}
        log_introspection_access("explain", detail=detail)
        output = build_explanation(task_id=args.task_id, routine_id=args.routine_id)
        print(serialize_output(output))
        return 0

    if args.command == "simulate":
        if args.task_file:
            task_payload = _load_json(Path(args.task_file))
            detail = {"task_file": args.task_file}
            log_introspection_access("simulate", detail=detail)
            output = build_simulation(task_payload=task_payload)
            print(serialize_output(output))
            return 0
        if args.routine_id:
            log_introspection_access("simulate", detail={"routine_id": args.routine_id})
            output = build_simulation(routine_id=args.routine_id)
            print(serialize_output(output))
            return 0
        if args.adapter:
            adapter_id, action = args.adapter
            log_introspection_access("simulate", detail={"adapter_id": adapter_id, "action": action})
            output = build_simulation(adapter_id=adapter_id, adapter_action=action)
            print(serialize_output(output))
            return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
