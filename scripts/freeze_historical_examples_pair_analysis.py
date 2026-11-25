#!/usr/bin/env python3
"""Freeze descriptive analysis rules for a prepared paired intervention cohort."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentientos.developmental_history_intervention_experiment import (
    MAX_EXPERIMENT_ARTIFACT_BYTES,
)
from sentientos.historical_examples_analysis_plan import (
    freeze_analysis_plan, verify_analysis_plan)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("historical_examples_analysis_duplicate_key")
        value[key] = item
    return value


def _read_cohort(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("historical_examples_analysis_cohort_not_regular")
    if path.stat().st_size > MAX_EXPERIMENT_ARTIFACT_BYTES:
        raise ValueError("historical_examples_analysis_cohort_unbounded")
    try:
        value = json.loads(path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ValueError("historical_examples_analysis_nonstandard_json")))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("historical_examples_analysis_cohort_unreadable") from exc
    if not isinstance(value, dict):
        raise ValueError("historical_examples_analysis_cohort_invalid")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-plan", type=Path)
    scoring = parser.add_mutually_exclusive_group()
    scoring.add_argument("--require-independent-scorer", action="store_true",
        dest="require_independent_scorer",
        help="explicitly require the pinned raw-receipt rescoring path (default)")
    scoring.add_argument("--legacy-same-process-scoring", action="store_false",
        dest="require_independent_scorer",
        help="reproduce a historical v1 plan without independent rescoring")
    parser.set_defaults(require_independent_scorer=True)
    args = parser.parse_args()
    cohort = _read_cohort(args.cohort)
    if args.verify_plan is not None:
        if args.output is not None:
            raise ValueError("historical_examples_analysis_verify_output_conflict")
        verification = verify_analysis_plan(cohort=cohort,
            plan=_read_cohort(args.verify_plan))
        print(json.dumps(verification, sort_keys=True, indent=2))
        return 0
    if args.output is None:
        raise ValueError("historical_examples_analysis_output_required")
    plan = freeze_analysis_plan(cohort,
        require_independent_scorer=args.require_independent_scorer)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(plan, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"analysis_plan_digest": plan["analysis_plan_digest"],
        "cohort_digest": plan["cohort_digest"],
        "trial_count": plan["trial_count"],
        "outcomes_observed": False, "learning_established": False},
        sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
