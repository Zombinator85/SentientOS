from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sentientos.household_presence_camera_capture_review_packet import (
    build_default_policy,
    evaluate_capture_review_packet,
    validate_policy,
)


def _read(p: str) -> dict[str, Any]:
    obj = json.loads(Path(p).read_text(encoding="utf-8"))
    return dict(obj) if isinstance(obj, dict) else {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "command",
        choices=["build-default", "evaluate", "validate", "summarize", "inspect-fixture"],
    )
    ap.add_argument("--input")
    ap.add_argument(
        "--fixtures-dir",
        default="tests/fixtures/household_presence_camera_capture_review_packet",
    )
    ap.add_argument("--fixture-name")
    ap.add_argument("--output")
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()

    out: dict[str, Any]

    if a.command == "build-default":
        out = {"policy": build_default_policy().__dict__}
    elif a.command == "validate":
        out = validate_policy(build_default_policy())
    elif a.command == "inspect-fixture":
        out = _read(str(Path(a.fixtures_dir) / str(a.fixture_name)))
    else:
        payload = _read(a.input) if a.input else {}
        res = evaluate_capture_review_packet(payload)
        if a.command == "evaluate":
            out = res.to_dict()
        else:
            out = {
                "status": res.status,
                "digest": res.packet.digest,
                "findings": [f.__dict__ for f in res.report.findings],
            }

    text = json.dumps(out, sort_keys=True, indent=2)
    print(text)

    if a.output:
        Path(a.output).write_text(text + "\n", encoding="utf-8")

    status = str(out.get("status", ""))
    return 1 if "blocked" in status or status.endswith(("invalid", "failed")) else 0


if __name__ == "__main__":
    raise SystemExit(main())