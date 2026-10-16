"""Prepare blinded fresh-session packets from canonical admitted history."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from sentientos.codex_transfer_packet import build_codex_transfer_packets, packet_json_bytes
from sentientos.codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK, RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from sentientos.resident_developmental_cognition import CONFIG_ENV, load_config
from sentientos.resident_developmental_writeback import ResidentDevelopmentalWritebackController
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionVerifier


def build(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config(args.config)
    ledger = AdmissionLedger(config.state_root / "runtime_admissions.json")
    writeback = ResidentDevelopmentalWritebackController(
        history_root=config.history_root,
        admission_verifier=RuntimeAdmissionVerifier(definitions={
            RESIDENT_DEVELOPMENTAL_WRITEBACK: RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION},
            ledger=ledger), current_sequence=ledger.current_sequence)
    model_settings = json.loads(Path(args.model_settings).read_text(encoding="utf-8"))
    scoring_plan = json.loads(Path(args.scoring_plan).read_text(encoding="utf-8"))
    if not isinstance(scoring_plan, dict) or set(scoring_plan) != {
            "probe_inputs", "multiplier", "offset", "applicability_basis"}:
        raise ValueError("scoring_plan_schema_invalid")
    result = build_codex_transfer_packets(writeback=writeback,
        history_record_id=args.history_record_id,
        irrelevant_record_id=args.irrelevant_record_id,
        adverse_record_id=args.adverse_record_id, family=args.family,
        irrelevant_family=args.irrelevant_family,
        probe_inputs=tuple(scoring_plan["probe_inputs"]),
        multiplier=scoring_plan["multiplier"], offset=scoring_plan["offset"],
        applicability_basis=scoring_plan["applicability_basis"],
        model_settings=model_settings)
    subject_dir = Path(args.subject_output_dir).resolve()
    scorer_dir = Path(args.scorer_output_dir).resolve()
    prereg_path = Path(args.preregistration_output).resolve()
    destinations = (subject_dir, scorer_dir, prereg_path)
    if any(left == right or left in right.parents or right in left.parents
            for index, left in enumerate(destinations)
            for right in destinations[index + 1:]):
        raise ValueError("subject_scorer_and_preregistration_destinations_must_be_separate")
    if any(path.exists() for path in destinations):
        raise FileExistsError("packet_output_destination_already_exists")
    subject_dir.mkdir(parents=True, exist_ok=False)
    scorer_dir.mkdir(parents=True, exist_ok=False)
    prereg_path.parent.mkdir(parents=True, exist_ok=True)
    for packet_id, packet in result["subject_packets"].items():
        (subject_dir / f"{packet_id}.json").write_bytes(packet_json_bytes(packet))
    (scorer_dir / "scorer_manifest.json").write_bytes(
        packet_json_bytes(result["scorer_manifest"]))
    prereg_path.write_bytes(packet_json_bytes(result["preregistration"]))
    return {"packet_count": len(result["subject_packets"]),
        "subject_packet_dir": str(subject_dir),
        "scorer_manifest": str(scorer_dir / "scorer_manifest.json"),
        "preregistration": str(prereg_path),
        "commitment": result["scorer_manifest"]["task_commitment"],
        "warning": "Keep scorer_only separate from every subject session."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=os.environ.get(CONFIG_ENV),
        help="configured resident developmental cognition file")
    parser.add_argument("--history-record-id", required=True)
    parser.add_argument("--irrelevant-record-id", required=True)
    parser.add_argument("--adverse-record-id", required=True)
    parser.add_argument("--family", required=True)
    parser.add_argument("--irrelevant-family", required=True)
    parser.add_argument("--scoring-plan", required=True,
        help="Private JSON containing probe_inputs, multiplier, offset, and applicability_basis")
    parser.add_argument("--model-settings", required=True,
        help="JSON file recording the same visible model/effort/generation settings for all sessions")
    parser.add_argument("--subject-output-dir", required=True,
        help="new directory containing subject-visible packet JSON only")
    parser.add_argument("--scorer-output-dir", required=True,
        help="new private directory for scorer-only material")
    parser.add_argument("--preregistration-output", required=True,
        help="separate preregistration artifact path to archive before subject sessions")
    args = parser.parse_args()
    if not args.config:
        parser.error(f"--config or {CONFIG_ENV} is required")
    print(json.dumps(build(args), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
