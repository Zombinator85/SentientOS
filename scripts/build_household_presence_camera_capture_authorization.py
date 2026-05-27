from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sentientos.household_presence_camera_capture_authorization import (
    build_default_policy,
    evaluate_capture_authorization,
    validate_policy,
)


def _read(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return dict(payload)
    return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=["build-default", "evaluate", "validate", "summarize", "inspect-fixture"],
    )
    parser.add_argument("--input")
    parser.add_argument(
        "--fixtures-dir",
        default="tests/fixtures/household_presence_camera_capture_authorization",
    )
    parser.add_argument("--output")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--fixture-name")
    args = parser.parse_args()

    output: dict[str, Any] = {}
    if args.command == "build-default":
        output = {"policy": build_default_policy().__dict__}
    elif args.command == "validate":
        output = validate_policy(build_default_policy())
    elif args.command == "inspect-fixture":
        output = _read(str(Path(args.fixtures_dir) / str(args.fixture_name)))
    else:
        payload = _read(args.input) if args.input else {}
        result = evaluate_capture_authorization(payload)
        output = result.to_dict()

    text = json.dumps(output, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)

    status = output.get("status")
    if isinstance(status, str) and (
        status.startswith("capture_authorization_blocked")
        or status == "capture_authorization_failed"
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
