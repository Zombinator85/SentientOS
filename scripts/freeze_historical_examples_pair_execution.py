#!/usr/bin/env python3
"""Freeze or verify a task-level historical-examples execution plan."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from work.historical_examples_intervention import (
    HistoricalExamplesInterventionError,
    make_historical_examples_pair_execution_plan,
    validate_historical_examples_pair_execution_plan,
)


def _read_object(path: Path, *, code: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError(code + "_file_invalid")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(code + "_duplicate_json_key")
            value[key] = item
        return value

    def reject_constant(value: str) -> None:
        raise ValueError(code + "_invalid_json_constant:" + value)

    try:
        result = json.loads(path.read_text(encoding="utf-8"),
            object_pairs_hook=unique_object, parse_constant=reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(code + "_unreadable") from exc
    if not isinstance(result, dict):
        raise ValueError(code + "_object_required")
    return result


def _write_new(path: Path, value: dict[str, Any]) -> None:
    target = path.absolute()
    if (target.exists() or target.is_symlink()
            or not target.parent.is_dir() or target.parent.is_symlink()):
        raise ValueError("historical_examples_pair_plan_output_invalid")
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True,
        indent=2, allow_nan=False) + "\n").encode("utf-8")
    descriptor = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            target.unlink()
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", required=True, type=Path)
    parser.add_argument("--analysis-plan", required=True, type=Path)
    parser.add_argument("--runner-cycle-id", action="append", required=True,
        help="one unique rootless runner ID per cohort trial, in cohort order")
    parser.add_argument("--backend-seed", required=True, type=int,
        help="fixed seed shared by the frozen model identity across all pairs")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-plan", type=Path)
    args = parser.parse_args(argv)
    try:
        cohort = _read_object(args.cohort, code="historical_examples_pair_cohort")
        analysis_plan = _read_object(args.analysis_plan,
            code="historical_examples_pair_analysis_plan")
        if args.verify_plan is not None:
            if args.output is not None:
                raise ValueError("historical_examples_pair_plan_verify_output_conflict")
            plan = _read_object(args.verify_plan,
                code="historical_examples_pair_execution_plan")
            canonical = validate_historical_examples_pair_execution_plan(
                cohort=cohort, analysis_plan=analysis_plan,
                runner_cycle_ids=args.runner_cycle_id,
                backend_seed=args.backend_seed, plan=plan)
            print(json.dumps({"execution_plan_digest":
                canonical["execution_plan_digest"],
                "cohort_digest": canonical["cohort_digest"],
                "trial_count": canonical["trial_count"],
                "outcomes_observed": False, "model_invoked": False,
                "learning_established": False, "authority": False},
                sort_keys=True))
            return 0
        if args.output is None:
            raise ValueError("historical_examples_pair_plan_output_required")
        plan = make_historical_examples_pair_execution_plan(
            cohort=cohort, analysis_plan=analysis_plan,
            runner_cycle_ids=args.runner_cycle_id,
            backend_seed=args.backend_seed)
        _write_new(args.output, plan)
        print(json.dumps({"execution_plan_digest":
            plan["execution_plan_digest"],
            "cohort_digest": plan["cohort_digest"],
            "trial_count": plan["trial_count"],
            "output": str(args.output.absolute()),
            "model_invoked": False, "learning_established": False,
            "authority": False}, sort_keys=True))
        return 0
    except (HistoricalExamplesInterventionError, OSError, TypeError,
            ValueError) as exc:
        print(f"historical examples pair plan failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
