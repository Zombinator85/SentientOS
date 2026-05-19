from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.work_item_lifecycle_dry_run_adapter import (
    WorkItemLifecycleDryRunAdapterRequest,
    run_work_item_lifecycle_dry_run_adapter,
)


def _exit_code(status: str) -> int:
    return 0 if status == "dry_run_adapter_completed" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run metadata-only work item dry-run lifecycle adapter")
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--handoff", required=True, type=Path)
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)

    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
    result = run_work_item_lifecycle_dry_run_adapter(
        WorkItemLifecycleDryRunAdapterRequest(
            packet=packet,
            handoff_plan=handoff,
            workspace_root=args.workspace_root,
            request_dry_run=True,
            artifact_output_path=str(args.output) if args.output else None,
        )
    )
    payload = result.to_dict()
    if args.output:
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.summary or not args.output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return _exit_code(result.adapter_status)


if __name__ == "__main__":
    raise SystemExit(main())
