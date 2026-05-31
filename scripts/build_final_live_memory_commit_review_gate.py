from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sentientos.final_live_memory_commit_review_gate import (
    FinalLiveCommitReviewPolicy,
    build_default_policy,
    evaluate_final_live_memory_commit_review_gate,
    validate_policy,
)


def _read(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    return dict(obj) if isinstance(obj, dict) else {}


def _policy(payload: dict[str, Any]) -> FinalLiveCommitReviewPolicy:
    raw = payload.get("policy")
    if isinstance(raw, dict):
        allowed = set(FinalLiveCommitReviewPolicy.__dataclass_fields__)
        return FinalLiveCommitReviewPolicy(**{str(k): v for k, v in raw.items() if str(k) in allowed})
    return build_default_policy()


def _fixture_path(fixtures_dir: str, input_name: str | None, fixture_name: str | None) -> Path:
    name = fixture_name or input_name or ""
    path = Path(name)
    if path.is_file():
        return path
    return Path(fixtures_dir) / name


def _bad(status: str) -> bool:
    return status in {"final_live_commit_review_blocked", "final_live_commit_review_invalid", "final_live_commit_review_failed"} or "blocked" in status or status.endswith(("invalid", "failed"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or evaluate final live-memory commit review gate metadata packets.")
    parser.add_argument("command", choices=["build-default", "evaluate", "validate", "summarize", "inspect-fixture"])
    parser.add_argument("--input")
    parser.add_argument("--fixtures-dir", default="tests/fixtures/final_live_memory_commit_review_gate")
    parser.add_argument("--fixture-name")
    parser.add_argument("--fixture")
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
        if args.command == "validate" and "real_root_admission_packet" not in payload and "real_memory_root_admission_packet" not in payload:
            out = validate_policy(_policy(payload))
        else:
            result = evaluate_final_live_memory_commit_review_gate(payload, _policy(payload))
            if args.command == "summarize" or args.summary:
                out = {
                    "status": result.status,
                    "digest": result.digest,
                    "packet_digest": result.packet.digest if result.packet else "",
                    "summary_counts": dict(result.report.summary_counts),
                    "finding_codes": [finding.code for finding in result.report.findings],
                }
            else:
                out = result.to_dict()

    print(json.dumps(out, indent=2, sort_keys=True))
    return 1 if _bad(str(out.get("status", ""))) else 0


if __name__ == "__main__":
    raise SystemExit(main())
