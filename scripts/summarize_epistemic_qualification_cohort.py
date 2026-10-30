from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sentientos.epistemic_qualification_cohort import (
    MAX_REPORT_BYTES,
    summarize_qualification_reports,
)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("epistemic_cohort_duplicate_json_key")
        result[key] = value
    return result


def _read_report(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) > MAX_REPORT_BYTES:
        raise ValueError("epistemic_cohort_report_limit_exceeded")
    value = json.loads(raw, object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise ValueError("epistemic_cohort_report_object_required")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Summarize supplied model-bound epistemic qualification reports.")
    parser.add_argument("reports", nargs="+", type=Path,
        help="JSON report files; inputs are read only")
    args = parser.parse_args(argv)
    try:
        result = summarize_qualification_reports(
            [_read_report(path) for path in args.reports])
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
