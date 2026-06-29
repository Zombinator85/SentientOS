#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sentientos.codex_workcell_storage_operator_consent_evidence_dossier import (
    CodexWorkcellStorageOperatorConsentEvidenceDossierError,
    INPUT_SPECS,
    build_codex_workcell_storage_operator_consent_evidence_dossier,
    omitted_input,
    read_json_input,
    render_codex_workcell_storage_operator_consent_evidence_dossier_markdown,
)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a metadata-only Codex workcell storage operator consent evidence dossier.")
    parser.add_argument("--output", required=True)
    for input_id in INPUT_SPECS:
        parser.add_argument("--" + input_id.replace("_", "-"), dest=input_id)
    parser.add_argument("--commit-sha")
    parser.add_argument("--pr-number")
    parser.add_argument("--pr-title")
    parser.add_argument("--markdown-output")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    summaries: dict[str, dict[str, object]] = {}
    reports: dict[str, dict[str, object]] = {}
    try:
        for input_id in INPUT_SPECS:
            path = getattr(args, input_id)
            if path:
                summaries[input_id], reports[input_id] = read_json_input(path, input_id)
            else:
                summaries[input_id] = omitted_input(input_id)
        dossier = build_codex_workcell_storage_operator_consent_evidence_dossier(input_summaries=summaries, input_reports=reports, commit_sha=args.commit_sha, pr_number=args.pr_number, pr_title=args.pr_title)
    except CodexWorkcellStorageOperatorConsentEvidenceDossierError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    Path(args.output).write_text(json.dumps(dossier, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if args.markdown_output:
        Path(args.markdown_output).write_text(render_codex_workcell_storage_operator_consent_evidence_dossier_markdown(dossier), encoding="utf-8")
    if args.summary:
        print(json.dumps({"storage_operator_consent_evidence_dossier_id": dossier["storage_operator_consent_evidence_dossier_id"], "consent_evidence_status": dossier["consent_evidence_status"], "supplied_report_count": dossier["evidence_dossier_context"]["supplied_report_count"], "active_storage_allowed_now": dossier["active_storage_allowed_now"]}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
