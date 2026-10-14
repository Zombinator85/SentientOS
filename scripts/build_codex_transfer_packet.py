"""Prepare blinded fresh-session packets from canonical admitted history."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sentientos.codex_transfer_packet import build_codex_transfer_packets, packet_json_bytes
from sentientos.resident_developmental_writeback import DevelopmentalHistoryStore


def build(args: argparse.Namespace) -> dict[str, Any]:
    store = DevelopmentalHistoryStore(Path(args.history_root))
    model_settings = json.loads(Path(args.model_settings).read_text(encoding="utf-8"))
    scoring_plan = json.loads(Path(args.scoring_plan).read_text(encoding="utf-8"))
    if not isinstance(scoring_plan, dict) or set(scoring_plan) != {
            "probe_inputs", "multiplier", "offset", "applicability_basis"}:
        raise ValueError("scoring_plan_schema_invalid")
    result = build_codex_transfer_packets(history_store=store,
        history_record_id=args.history_record_id,
        irrelevant_record_id=args.irrelevant_record_id,
        adverse_record_id=args.adverse_record_id, family=args.family,
        irrelevant_family=args.irrelevant_family,
        probe_inputs=tuple(scoring_plan["probe_inputs"]),
        multiplier=scoring_plan["multiplier"], offset=scoring_plan["offset"],
        applicability_basis=scoring_plan["applicability_basis"],
        model_settings=model_settings)
    output = Path(args.output_dir)
    subject_dir = output / "subject_packets"
    scorer_dir = output / "scorer_only"
    subject_dir.mkdir(parents=True, exist_ok=False)
    scorer_dir.mkdir(parents=True, exist_ok=False)
    for packet_id, packet in result["subject_packets"].items():
        (subject_dir / f"{packet_id}.json").write_bytes(packet_json_bytes(packet))
    (scorer_dir / "scorer_manifest.json").write_bytes(
        packet_json_bytes(result["scorer_manifest"]))
    return {"packet_count": len(result["subject_packets"]),
        "subject_packet_dir": str(subject_dir),
        "scorer_manifest": str(scorer_dir / "scorer_manifest.json"),
        "commitment": result["scorer_manifest"]["task_commitment"],
        "warning": "Keep scorer_only separate from every subject session."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-root", required=True)
    parser.add_argument("--history-record-id", required=True)
    parser.add_argument("--irrelevant-record-id", required=True)
    parser.add_argument("--adverse-record-id", required=True)
    parser.add_argument("--family", required=True)
    parser.add_argument("--irrelevant-family", required=True)
    parser.add_argument("--scoring-plan", required=True,
        help="Private JSON containing probe_inputs, multiplier, offset, and applicability_basis")
    parser.add_argument("--model-settings", required=True,
        help="JSON file recording the same visible model/effort/generation settings for all sessions")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
