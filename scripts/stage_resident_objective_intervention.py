#!/usr/bin/env python3
"""Stage one bounded resident history-intervention request; never invoke a model."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentientos.developmental_model_replacement_experiment import ObjectivePredictionTask
from sentientos.resident_developmental_cognition import (
    CONFIG_ENV,
    ResidentDevelopmentalCognitionError,
    inspect_checkpointed_history_record_refs,
    load_config,
    objective_request_payload,
    stage_objective_request,
)
from sentientos.codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK, RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from sentientos.resident_developmental_writeback import ResidentDevelopmentalWritebackController
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionVerifier


def stage_request(*, config_path: str | Path, request_id: str,
        task: ObjectivePredictionTask) -> tuple[Path, dict[str, object], int]:
    """Stage only after read-only verification of committed eligible history."""
    config = load_config(config_path)
    if not config.enabled or not config.comparison_enabled:
        raise ResidentDevelopmentalCognitionError("history_comparison_not_enabled")
    ledger = AdmissionLedger(config.state_root / "runtime_admissions.json")
    writeback = ResidentDevelopmentalWritebackController(
        history_root=config.history_root,
        admission_verifier=RuntimeAdmissionVerifier(
            definitions={RESIDENT_DEVELOPMENTAL_WRITEBACK:
                RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}, ledger=ledger),
        current_sequence=ledger.current_sequence)
    refs = inspect_checkpointed_history_record_refs(
        config.state_root / "composition_state.json", writeback=writeback,
        limit=config.max_retrieved_records)
    if not refs:
        raise ResidentDevelopmentalCognitionError(
            "objective_intervention_requires_checkpointed_history")
    payload = objective_request_payload(request_id=request_id, task=task)
    path = stage_objective_request(config.state_root, request_id=request_id, task=task)
    return path, dict(payload), len(refs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=os.environ.get(CONFIG_ENV),
        help="configured resident developmental cognition file")
    parser.add_argument("--request-id", required=True,
        help="unique operator-selected identity for this one-shot request")
    parser.add_argument("--multiplier", type=int, required=True)
    parser.add_argument("--offset", type=int, required=True)
    parser.add_argument("--probe", type=int, action="append", required=True,
        help="held-out integer probe; repeat for an exact-scored suite (maximum 16)")
    args = parser.parse_args()
    if not args.config:
        parser.error(f"--config or {CONFIG_ENV} is required")
    if os.name != "posix":
        parser.exit(2, "blocked: this bounded private-file publisher is currently POSIX-only\n")
    if not 1 <= len(args.probe) <= 16:
        parser.error("one to sixteen distinct --probe values are required")
    task = ObjectivePredictionTask(args.multiplier, args.offset, args.probe[0],
        tuple(args.probe[1:]))
    try:
        path, payload, history_record_count = stage_request(
            config_path=args.config, request_id=args.request_id, task=task)
    except (ResidentDevelopmentalCognitionError, OSError, ValueError) as exc:
        parser.exit(2, f"blocked: {exc}\n")
    print(json.dumps({"status": "staged_not_authorized", "path": str(path),
        "request_id": args.request_id, "request_digest": payload["request_digest"],
        "task_descriptor": payload["task_descriptor"],
        "verified_checkpointed_history_record_count": history_record_count,
        "model_invoked": False,
        "serving_activated": False, "authority_granted": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
