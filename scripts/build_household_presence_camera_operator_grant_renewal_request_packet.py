from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sentientos.household_presence_camera_operator_grant_renewal_request_packet import (
    HouseholdCameraOperatorGrantRenewalRequestPolicy,
    build_default_policy,
    evaluate_operator_grant_renewal_request_packet,
    validate_policy,
)


def _read(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    return dict(obj) if isinstance(obj, dict) else {}


def _policy(payload: dict[str, Any]) -> HouseholdCameraOperatorGrantRenewalRequestPolicy:
    policy_payload = payload.get("policy")
    if isinstance(policy_payload, dict):
        allowed = set(HouseholdCameraOperatorGrantRenewalRequestPolicy.__dataclass_fields__)
        return HouseholdCameraOperatorGrantRenewalRequestPolicy(**{k: v for k, v in policy_payload.items() if k in allowed})
    return build_default_policy()


def _fixture_path(fixtures_dir: str, input_name: str | None, fixture_name: str | None) -> Path:
    name = fixture_name or input_name or ""
    p = Path(name)
    if p.is_file():
        return p
    return Path(fixtures_dir) / name


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["build-default", "evaluate", "validate", "summarize", "inspect-fixture"])
    parser.add_argument("--input")
    parser.add_argument("--fixtures-dir", default="tests/fixtures/household_presence_camera_operator_grant_renewal_request_packet")
    parser.add_argument("--fixture-name")
    parser.add_argument("--fixture")
    parser.add_argument("--output")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    if args.command == "build-default":
        out: dict[str, Any] = {"policy": asdict(build_default_policy())}
    elif args.command == "inspect-fixture":
        out = _read(str(_fixture_path(args.fixtures_dir, args.input, args.fixture_name or args.fixture)))
    elif args.command == "validate" and not args.input:
        out = validate_policy(build_default_policy())
    else:
        payload = _read(args.input)
        if args.command == "validate" and "trend_ledger" not in payload and "ledger" not in payload:
            out = validate_policy(_policy(payload))
        else:
            result = evaluate_operator_grant_renewal_request_packet(payload, _policy(payload))
            if args.command == "summarize" or args.summary:
                out = {"status": result.status, "digest": result.packet.digest, "summary_counts": result.report.summary_counts, "finding_codes": [f.code for f in result.report.findings]}
            else:
                out = result.to_dict()

    text = json.dumps(out, indent=2, sort_keys=True)
    print(text)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    status = str(out.get("status", ""))
    return 1 if "blocked" in status or status.endswith(("invalid", "failed")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
