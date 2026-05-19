from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sentientos.work_item_intake import normalize_work_item_intake, summarize_work_item_packet


def _exit_code(status: str) -> int:
    if status in {"intake_blocked", "intake_contradicted", "intake_insufficient_metadata"}:
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize a metadata-only work item intake packet.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--derive-workspace-proposal", action="store_true")
    args = parser.parse_args(argv)

    payload: dict[str, Any] = json.loads(args.input.read_text(encoding="utf-8"))
    packet, _ = normalize_work_item_intake(payload, derive_workspace_proposal=args.derive_workspace_proposal)
    summary = summarize_work_item_packet(packet)

    if args.output:
        args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.summary or not args.output:
        print(json.dumps(summary, indent=2, sort_keys=True))

    return _exit_code(packet.intake_status)


if __name__ == "__main__":
    raise SystemExit(main())
