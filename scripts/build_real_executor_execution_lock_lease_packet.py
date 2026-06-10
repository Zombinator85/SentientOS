#!/usr/bin/env python3
"""CLI for deterministic real executor execution lock lease packet metadata."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sentientos.real_executor_execution_lock_lease_packet import (  # noqa: E402
    FAIL_STATUSES,
    build_default_policy,
    evaluate_real_executor_execution_lock_lease_packet,
    validate_policy,
)

FIXTURE_ROOT = Path("tests/fixtures/real_executor_execution_lock_lease_packet")


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _emit(payload: Any) -> None:
    print(json.dumps(payload, sort_keys=True, indent=2))


def _exit_for(status: str) -> int:
    return 1 if status in FAIL_STATUSES or status.endswith("_blocked") or status.endswith("_invalid") or status.endswith("_failed") else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build-default")
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("packet", nargs="?", type=Path)
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("packet", type=Path)
    summarize = sub.add_parser("summarize")
    summarize.add_argument("packet", type=Path)
    inspect = sub.add_parser("inspect-fixture")
    inspect.add_argument("name")
    args = parser.parse_args(argv)

    if args.command == "build-default":
        policy = build_default_policy()
        _emit({"policy": policy.to_dict(), "validation": validate_policy(policy), "fixture_root": str(FIXTURE_ROOT)})
        return 0
    if args.command == "validate" and args.packet is None:
        policy_result = validate_policy(build_default_policy())
        _emit(policy_result)
        return _exit_for(str(policy_result["status"]))
    if args.command == "inspect-fixture":
        target = FIXTURE_ROOT / args.name
        _emit(_load(target))
        return 0
    result = evaluate_real_executor_execution_lock_lease_packet(_load(args.packet))
    payload = result.to_dict()
    if args.command == "summarize":
        _emit({
            "status": result.status,
            "packet_digest": result.packet.digest if result.packet else "",
            "result_digest": result.digest,
            "summary_counts": result.report.summary_counts,
            "findings": [finding.to_dict() for finding in result.report.findings],
        })
    else:
        _emit(payload)
    return _exit_for(result.status)


if __name__ == "__main__":
    raise SystemExit(main())
