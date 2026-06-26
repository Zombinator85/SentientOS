#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sentientos.codex_workcell_storage_execution_dossier import (
    CodexWorkcellStorageExecutionDossierError,
    INPUT_SPECS,
    build_codex_workcell_storage_execution_dossier,
    omitted_input,
    read_json_input,
    render_codex_workcell_storage_execution_dossier_markdown,
)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a metadata-only Codex workcell storage execution readiness dossier.")
    parser.add_argument("--output", required=True)
    for input_id, _, _ in INPUT_SPECS:
        parser.add_argument("--" + input_id.replace("_", "-"), dest=input_id)
    parser.add_argument("--commit-sha")
    parser.add_argument("--pr-number")
    parser.add_argument("--pr-title")
    parser.add_argument("--markdown-output")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    summaries = {}; reports = {}
    try:
        for input_id, _, _ in INPUT_SPECS:
            path = getattr(args, input_id)
            if path:
                summary, loaded = read_json_input(path, input_id)
                summaries[input_id] = summary; reports[input_id] = loaded
            else:
                summaries[input_id] = omitted_input(input_id)
        dossier = build_codex_workcell_storage_execution_dossier(input_summaries=summaries, input_reports=reports, commit_sha=args.commit_sha, pr_number=args.pr_number, pr_title=args.pr_title)
    except CodexWorkcellStorageExecutionDossierError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    Path(args.output).write_text(json.dumps(dossier, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if args.markdown_output:
        Path(args.markdown_output).write_text(render_codex_workcell_storage_execution_dossier_markdown(dossier), encoding="utf-8")
    if args.summary:
        print(json.dumps({"storage_execution_dossier_id": dossier["storage_execution_dossier_id"], "storage_execution_status": dossier["storage_execution_status"], "supplied_report_count": dossier["dossier_context"]["supplied_report_count"], "active_storage_allowed_now": dossier["active_execution_gap_summary"]["active_storage_allowed_now"]}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
