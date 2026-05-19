from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.work_item_dry_run_closure import WorkItemDryRunClosureRequest, build_work_item_dry_run_closure_manifest


def _exit_code(status: str) -> int:
    return 2 if status in {"dry_run_closed_contradicted", "dry_run_closure_insufficient_evidence"} else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build metadata-only work-item dry-run closure manifest")
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--handoff", type=Path)
    parser.add_argument("--dry-run-result", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)

    packet = json.loads(args.packet.read_text(encoding="utf-8")) if args.packet else None
    handoff = json.loads(args.handoff.read_text(encoding="utf-8")) if args.handoff else None
    dry = json.loads(args.dry_run_result.read_text(encoding="utf-8")) if args.dry_run_result else None

    result = build_work_item_dry_run_closure_manifest(
        WorkItemDryRunClosureRequest(packet=packet, handoff_plan=handoff, dry_run_result=dry, closure_artifact_output_path=str(args.output) if args.output else None)
    )
    payload = result.to_dict()
    if args.output:
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.summary or not args.output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return _exit_code(result.manifest.closure_status)


if __name__ == "__main__":
    raise SystemExit(main())
