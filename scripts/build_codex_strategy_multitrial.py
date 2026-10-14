"""Prepare blinded packets for multiple distinct strategy situations."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sentientos.codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK, RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from sentientos.codex_strategy_multitrial import build_operator_codex_strategy_multitrial
from sentientos.embodied_consequence import canonical_bytes
from sentientos.resident_developmental_cognition import CONFIG_ENV, load_config
from sentientos.resident_developmental_writeback import ResidentDevelopmentalWritebackController
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionVerifier


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=os.environ.get(CONFIG_ENV))
    parser.add_argument("--history-record-id", required=True)
    parser.add_argument("--trials", required=True,
        help="private JSON mapping at least two opaque trial IDs to frozen situations")
    parser.add_argument("--model-settings", required=True)
    parser.add_argument("--subject-output-dir", required=True)
    parser.add_argument("--scorer-manifest-output", required=True)
    parser.add_argument("--preregistration-output", required=True)
    args = parser.parse_args()
    if not args.config:
        parser.error(f"--config or {CONFIG_ENV} is required")
    config = load_config(args.config)
    ledger = AdmissionLedger(config.state_root / "runtime_admissions.json")
    writeback = ResidentDevelopmentalWritebackController(
        history_root=config.history_root,
        admission_verifier=RuntimeAdmissionVerifier(definitions={
            RESIDENT_DEVELOPMENTAL_WRITEBACK: RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION},
            ledger=ledger), current_sequence=ledger.current_sequence)
    trials = json.loads(Path(args.trials).read_text(encoding="utf-8"))
    settings = json.loads(Path(args.model_settings).read_text(encoding="utf-8"))
    result = build_operator_codex_strategy_multitrial(writeback=writeback,
        history_record_id=args.history_record_id, trials=trials, model_settings=settings)
    subject_dir = Path(args.subject_output_dir).resolve()
    scorer_path = Path(args.scorer_manifest_output).resolve()
    prereg_path = Path(args.preregistration_output).resolve()
    destinations = (subject_dir, scorer_path, prereg_path)
    if any(left == right or left in right.parents or right in left.parents
            for index, left in enumerate(destinations) for right in destinations[index + 1:]):
        raise ValueError("strategy_multitrial_destinations_must_be_separate")
    if any(path.exists() for path in destinations):
        raise FileExistsError("strategy_multitrial_destination_already_exists")
    subject_dir.mkdir(parents=True, exist_ok=False)
    scorer_path.parent.mkdir(parents=True, exist_ok=True)
    prereg_path.parent.mkdir(parents=True, exist_ok=True)
    for packet_id, packet in result["subject_packets"].items():
        (subject_dir / f"{packet_id}.json").write_bytes(canonical_bytes(packet) + b"\n")
    scorer_path.write_bytes(canonical_bytes(result["scorer_manifest"]) + b"\n")
    prereg_path.write_bytes(canonical_bytes(result["preregistration"]) + b"\n")
    print(json.dumps({"task_count": len(trials),
        "packet_count": len(result["subject_packets"]),
        "subject_packet_dir": str(subject_dir), "scorer_manifest": str(scorer_path),
        "preregistration": str(prereg_path), "statistical_significance_claimed": False},
        sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
