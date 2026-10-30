from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sentientos.epistemic_evidence_revision_suite import MAX_REPORTS
from sentientos.epistemic_pressure_control_suite import (
    compose_pressure_control_revision_suite,
)
from sentientos.epistemic_qualification_cohort import MAX_REPORT_BYTES


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("pressure_control_suite_duplicate_json_key")
        result[key] = value
    return result


def _read_report(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) > MAX_REPORT_BYTES:
        raise ValueError("pressure_control_suite_report_limit_exceeded")
    value = json.loads(raw, object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise ValueError("pressure_control_suite_report_object_required")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify v2 revision evidence and compose one linked pressure-only control.")
    parser.add_argument("revision_suite", type=Path,
        help="the composed v2 revision suite report")
    parser.add_argument("series_reports", nargs="+", type=Path,
        help=f"one to {MAX_REPORTS} source reports used to build the v2 suite")
    parser.add_argument("--pressure-control", type=Path,
        help="one linked pressure-only control report; omission remains insufficient")
    args = parser.parse_args(argv)
    if len(args.series_reports) > MAX_REPORTS:
        parser.error("pressure_control_suite_report_count_invalid")
    try:
        result = compose_pressure_control_revision_suite(
            revision_suite_report=_read_report(args.revision_suite),
            revision_reports=[_read_report(path) for path in args.series_reports],
            pressure_control_report=(
                _read_report(args.pressure_control) if args.pressure_control else None),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
