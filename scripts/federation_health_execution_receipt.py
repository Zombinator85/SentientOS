"""Bind a generated Federation Health report to its GitHub Actions execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_ALLOWED_EVENTS = {"push", "schedule", "workflow_dispatch"}


def build_execution_receipt(
    *,
    run_id: str,
    run_attempt: str,
    event_name: str,
    ref: str,
    head_sha: str,
    report_path: Path,
) -> dict[str, Any]:
    """Create a small, non-secret receipt for a successful main-branch report."""
    if not run_id.isdecimal() or int(run_id) < 1:
        raise ValueError("workflow_run_id_invalid")
    if not run_attempt.isdecimal() or int(run_attempt) < 1:
        raise ValueError("workflow_run_attempt_invalid")
    if event_name not in _ALLOWED_EVENTS:
        raise ValueError("workflow_event_not_allowed")
    if ref != "refs/heads/main":
        raise ValueError("workflow_ref_not_main")
    if not _SHA_RE.fullmatch(head_sha):
        raise ValueError("workflow_head_sha_invalid")
    if not report_path.is_file():
        raise ValueError("federation_health_report_missing")

    report_bytes = report_path.read_bytes()
    return {
        "schema_version": "sentientos.federation_health_execution:v1",
        "workflow": "Federation Health Update",
        "workflow_run_id": int(run_id),
        "workflow_run_attempt": int(run_attempt),
        "event_name": event_name,
        "ref": ref,
        "head_sha": head_sha,
        "administrator_preflight": "passed",
        "health_generator": "completed_successfully",
        "report_path": "docs/FEDERATION_HEALTH.md",
        "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    receipt = build_execution_receipt(
        run_id=os.environ.get("FEDERATION_HEALTH_RUN_ID", ""),
        run_attempt=os.environ.get("FEDERATION_HEALTH_RUN_ATTEMPT", ""),
        event_name=os.environ.get("FEDERATION_HEALTH_EVENT_NAME", ""),
        ref=os.environ.get("FEDERATION_HEALTH_REF", ""),
        head_sha=os.environ.get("FEDERATION_HEALTH_HEAD_SHA", ""),
        report_path=args.report,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
