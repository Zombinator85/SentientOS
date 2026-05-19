from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.work_item_lifecycle_handoff import (
    plan_work_item_lifecycle_handoff,
    summarize_work_item_lifecycle_handoff_plan,
    WorkItemLifecycleHandoffRequest,
)


def _exit_code(surface: str) -> int:
    if surface in {
        "blocked_authority_request",
        "blocked_external_integration_request",
        "blocked_agent_execution_request",
        "insufficient_metadata",
        "needs_operator_clarification",
    }:
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build metadata-only work item lifecycle handoff plan")
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--emit-lifecycle-candidate", action="store_true")
    args = parser.parse_args(argv)

    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    plan = plan_work_item_lifecycle_handoff(
        WorkItemLifecycleHandoffRequest(packet=packet, emit_lifecycle_candidate=args.emit_lifecycle_candidate)
    )
    summary = summarize_work_item_lifecycle_handoff_plan(plan)

    if args.output:
        args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.summary or not args.output:
        print(json.dumps(summary, indent=2, sort_keys=True))
    return _exit_code(plan.recommended_next_governed_surface)


if __name__ == "__main__":
    raise SystemExit(main())
