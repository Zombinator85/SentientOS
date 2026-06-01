#!/usr/bin/env python3
"""CLI for live executor lock lease gate metadata."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

from sentientos.live_executor_lock_lease_gate import (
    FAIL_STATUSES,
    build_default_policy,
    evaluate_live_executor_lock_lease_gate,
    validate_policy,
)

FIXTURE_ROOT = Path("tests/fixtures/live_executor_lock_lease_gate")


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _emit(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build-default")
    evaluate = sub.add_parser("evaluate"); evaluate.add_argument("packet", type=Path)
    validate = sub.add_parser("validate"); validate.add_argument("packet", type=Path, nargs="?")
    summarize = sub.add_parser("summarize"); summarize.add_argument("packet", type=Path)
    inspect = sub.add_parser("inspect-fixture"); inspect.add_argument("name")
    args = parser.parse_args(argv)
    if args.command == "build-default":
        _emit({"policy": build_default_policy().__dict__, "validation": validate_policy()}); return 0
    if args.command == "inspect-fixture":
        name = args.name if str(args.name).endswith(".json") else f"{args.name}.json"
        _emit(_load(FIXTURE_ROOT / name)); return 0
    if args.command == "validate":
        if args.packet is None:
            policy_result = validate_policy(); _emit(policy_result); return 0 if policy_result["status"] == "valid" else 1
        eval_result = evaluate_live_executor_lock_lease_gate(_load(args.packet)); _emit(eval_result.to_dict()); return 0 if eval_result.status not in FAIL_STATUSES else 1
    if args.command == "evaluate":
        eval_result = evaluate_live_executor_lock_lease_gate(_load(args.packet)); _emit(eval_result.to_dict()); return 0 if eval_result.status not in FAIL_STATUSES else 1
    if args.command == "summarize":
        eval_result = evaluate_live_executor_lock_lease_gate(_load(args.packet))
        _emit({"status": eval_result.status, "digest": eval_result.digest, "packet_digest": eval_result.packet.digest if eval_result.packet else "", "summary_counts": eval_result.report.summary_counts, "findings": [f.to_dict() for f in eval_result.report.findings]})
        return 0 if eval_result.status not in FAIL_STATUSES else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
