#!/usr/bin/env python3
"""CPU-only verification of frozen pair slots against journal protocols."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentientos.developmental_history_intervention_experiment import (
    DevelopmentalExperimentStore,
)
from work.historical_examples_intervention import (
    HistoricalExamplesInterventionError,
    HistoricalExamplesPairJournal,
    _digest,
    validate_historical_examples_pair_execution_plan,
    validate_historical_examples_pair_execution_slot,
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", required=True, type=Path)
    parser.add_argument("--analysis-plan", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--journal-root", required=True, type=Path)
    parser.add_argument("--output", type=Path,
        help="optional new file for the answer-free audit report")
    args = parser.parse_args(argv)
    try:
        cohort = _read_object(args.cohort, code="historical_examples_pair_cohort")
        analysis_plan = _read_object(args.analysis_plan,
            code="historical_examples_pair_analysis_plan")
        plan = _read_object(args.plan, code="historical_examples_pair_plan")
        journal_root = args.journal_root.absolute()
        if journal_root.is_symlink() or not journal_root.is_dir():
            raise ValueError("historical_examples_pair_journal_root_invalid")
        trials = plan.get("trials")
        if not isinstance(trials, list) or not trials:
            raise ValueError("historical_examples_pair_plan_trials_invalid")
        runner_ids = [trial.get("runner_cycle_id")
            if isinstance(trial, dict) else None for trial in trials]
        backend_seeds = {trial.get("backend_seed")
            for trial in trials if isinstance(trial, dict)}
        if len(backend_seeds) != 1:
            raise ValueError("historical_examples_pair_backend_seed_mismatch")
        backend_seed = next(iter(backend_seeds))
        canonical = validate_historical_examples_pair_execution_plan(
            cohort=cohort, analysis_plan=analysis_plan,
            runner_cycle_ids=runner_ids, backend_seed=backend_seed, plan=plan)
        journal = HistoricalExamplesPairJournal(
            store=DevelopmentalExperimentStore(journal_root))
        verified = []
        for index, row in enumerate(canonical["trials"]):
            protocol = journal.load_protocol(
                protocol_digest=row["protocol_digest"])
            task = journal.load_task_for_protocol(
                protocol_digest=row["protocol_digest"])
            verified.append(validate_historical_examples_pair_execution_slot(
                plan=canonical, trial_index=index, protocol=protocol,
                objective_task=task, runner_cycle_id=row["runner_cycle_id"],
                backend_seed=backend_seed))
        semantic = {
            "schema_version": "sentientos.historical_examples_pair_execution_slot_audit:v1",
            "execution_plan_digest": canonical["execution_plan_digest"],
            "cohort_digest": canonical["cohort_digest"],
            "trial_count": len(verified), "verified_slots": verified,
            "all_slots_verified": True, "model_invoked": False,
            "learning_established": False, "authority": False}
        report = {**semantic, "verification_digest": _digest(semantic)}
        if args.output is not None:
            target = args.output.absolute()
            if (target.exists() or target.is_symlink()
                    or not target.parent.is_dir() or target.parent.is_symlink()):
                raise ValueError("historical_examples_pair_audit_output_invalid")
            payload = (json.dumps(report, ensure_ascii=False, sort_keys=True,
                indent=2, allow_nan=False) + "\n").encode("utf-8")
            descriptor = os.open(str(target),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
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
        print(json.dumps(report, sort_keys=True))
        return 0
    except (HistoricalExamplesInterventionError, OSError, TypeError,
            ValueError) as exc:
        print(f"historical examples execution slots failed: {exc}",
            file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
