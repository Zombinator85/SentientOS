#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sentientos.codex_workcell_storage_operator_consent_evidence_dossier_verifier import (
    ALL_INPUT_IDS,
    OPTIONAL_INPUT_IDS,
    REQUIRED_DOSSIER_INPUT_ID,
    CodexWorkcellStorageOperatorConsentEvidenceDossierVerifierError,
    omitted_input,
    read_json_input,
    render_codex_workcell_storage_operator_consent_evidence_dossier_verifier_markdown,
    verify_codex_workcell_storage_operator_consent_evidence_dossier,
)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a metadata-only Codex workcell storage operator consent evidence dossier.")
    parser.add_argument("--storage-operator-consent-evidence-dossier-json", dest=REQUIRED_DOSSIER_INPUT_ID, required=True)
    parser.add_argument("--output", required=True)
    for input_id in OPTIONAL_INPUT_IDS:
        parser.add_argument("--" + input_id.replace("_", "-"), dest=input_id)
    parser.add_argument("--markdown-output")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    summaries: dict[str, dict[str, object]] = {}
    reports: dict[str, dict[str, object]] = {}
    try:
        summaries[REQUIRED_DOSSIER_INPUT_ID], dossier = read_json_input(getattr(args, REQUIRED_DOSSIER_INPUT_ID), REQUIRED_DOSSIER_INPUT_ID)
        for input_id in OPTIONAL_INPUT_IDS:
            path = getattr(args, input_id)
            if path:
                summaries[input_id], reports[input_id] = read_json_input(path, input_id)
            else:
                summaries[input_id] = omitted_input(input_id)
        report = verify_codex_workcell_storage_operator_consent_evidence_dossier(evidence_dossier=dossier, input_summaries=summaries, optional_reports=reports)
    except CodexWorkcellStorageOperatorConsentEvidenceDossierVerifierError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    Path(args.output).write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if args.markdown_output:
        Path(args.markdown_output).write_text(render_codex_workcell_storage_operator_consent_evidence_dossier_verifier_markdown(report), encoding="utf-8")
    if args.summary:
        print(json.dumps({"storage_operator_consent_evidence_dossier_verifier_id": report["storage_operator_consent_evidence_dossier_verifier_id"], "verification_status": report["verification_status"], "active_storage_allowed_now": report["active_storage_allowed_now"], "violation_count": report["violation_summary"]["violation_count"]}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
