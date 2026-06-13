from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sentientos.real_live_memory_commit_adapter_readiness_gate import (  # noqa: E402
    FAIL_STATUSES,
    build_default_policy,
    evaluate_real_live_memory_commit_adapter_readiness_gate,
    validate_policy,
)

FIXTURE_ROOT = Path("tests/fixtures/real_live_memory_commit_adapter_readiness_gate")


def _load(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _emit(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def _fixture_path(name: str) -> Path:
    candidate = FIXTURE_ROOT / name
    if candidate.suffix != ".json":
        candidate = candidate.with_suffix(".json")
    if not candidate.is_file():
        raise FileNotFoundError(f"fixture not found: {candidate}")
    return candidate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build deterministic metadata-only real live memory commit adapter readiness gate evidence.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build-default")
    validate = sub.add_parser("validate")
    validate.add_argument("gate", nargs="?")
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("gate")
    summarize = sub.add_parser("summarize")
    summarize.add_argument("gate")
    inspect = sub.add_parser("inspect-fixture")
    inspect.add_argument("name")
    args = parser.parse_args(argv)

    if args.command == "build-default":
        _emit({"policy": build_default_policy().to_dict(), "validation": validate_policy(), "fixture_root": str(FIXTURE_ROOT)})
        return 0
    if args.command == "validate":
        if args.gate:
            result = evaluate_real_live_memory_commit_adapter_readiness_gate(_load(args.gate))
            _emit(result.to_dict())
            return 0 if result.status not in FAIL_STATUSES else 1
        validation_result = validate_policy()
        _emit(validation_result)
        return 0 if validation_result["status"] == "valid" else 1
    if args.command == "evaluate":
        result = evaluate_real_live_memory_commit_adapter_readiness_gate(_load(args.gate))
        _emit(result.to_dict())
        return 0 if result.status not in FAIL_STATUSES else 1
    if args.command == "summarize":
        result = evaluate_real_live_memory_commit_adapter_readiness_gate(_load(args.gate))
        _emit({
            "status": result.status,
            "digest": result.digest,
            "gate_digest": result.gate.digest if result.gate else "",
            "summary_counts": dict(result.report.summary_counts),
            "findings": [finding.to_dict() for finding in result.report.findings],
        })
        return 0 if result.status not in FAIL_STATUSES else 1
    if args.command == "inspect-fixture":
        _emit(json.loads(_fixture_path(args.name).read_text(encoding="utf-8")))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
