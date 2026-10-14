"""List privacy-bounded admitted history candidates for the Codex transfer pilot."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sentientos.codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK, RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from sentientos.codex_transfer_packet import discover_codex_transfer_records
from sentientos.resident_developmental_cognition import CONFIG_ENV, load_config
from sentientos.resident_developmental_writeback import ResidentDevelopmentalWritebackController
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionVerifier


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=os.environ.get(CONFIG_ENV),
        help="configured resident developmental cognition file")
    parser.add_argument("--output", help="optional JSON report path")
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
    report = {"schema_version": "sentientos.codex_transfer_record_inventory:v1",
        "read_only": True,
        "selection_limitations": [
            "Task-family agreement does not establish shared mapping applicability.",
            "The report omits observed answers and private oracle parameters."],
        "records": discover_codex_transfer_records(writeback=writeback)}
    encoded = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
