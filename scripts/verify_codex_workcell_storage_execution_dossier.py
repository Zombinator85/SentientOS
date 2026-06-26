#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sentientos.codex_workcell_storage_execution_dossier_verifier import (
    CodexWorkcellStorageExecutionDossierVerifierError,
    OPTIONAL_INPUT_IDS,
    omitted_input,
    read_json_input,
    render_codex_workcell_storage_execution_dossier_verifier_markdown,
    verify_codex_workcell_storage_execution_dossier,
)

def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description="Verify a metadata-only Codex workcell storage execution dossier JSON.")
    parser.add_argument("--storage-execution-dossier-json", required=True)
    parser.add_argument("--output", required=True)
    for input_id in OPTIONAL_INPUT_IDS:
        parser.add_argument("--" + input_id.replace("_", "-"), dest=input_id)
    parser.add_argument("--markdown-output")
    parser.add_argument("--summary", action="store_true")
    args=parser.parse_args(argv)
    try:
        dossier_summary, dossier = read_json_input(args.storage_execution_dossier_json, "storage_execution_dossier_json")
        optional_summaries={}; optional_reports={}
        for input_id in OPTIONAL_INPUT_IDS:
            path=getattr(args, input_id)
            if path:
                summary, report = read_json_input(path, input_id)
                optional_summaries[input_id]=summary; optional_reports[input_id]=report
            else:
                optional_summaries[input_id]=omitted_input(input_id)
        report = verify_codex_workcell_storage_execution_dossier(storage_execution_dossier=dossier, storage_execution_dossier_summary=dossier_summary, optional_reports=optional_reports, optional_summaries=optional_summaries)
    except CodexWorkcellStorageExecutionDossierVerifierError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    Path(args.output).write_text(json.dumps(report, sort_keys=True, indent=2)+"\n", encoding="utf-8")
    if args.markdown_output:
        Path(args.markdown_output).write_text(render_codex_workcell_storage_execution_dossier_verifier_markdown(report), encoding="utf-8")
    if args.summary:
        print(json.dumps({"storage_execution_dossier_verifier_id": report["storage_execution_dossier_verifier_id"], "verification_status": report["verification_status"], "violation_count": report["violation_summary"]["violation_count"], "warning_count": report["violation_summary"]["warning_count"]}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
