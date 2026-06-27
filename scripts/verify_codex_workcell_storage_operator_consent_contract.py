#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sentientos.codex_workcell_storage_operator_consent_verifier import (
    CodexWorkcellStorageOperatorConsentVerifierError,
    OPTIONAL_INPUT_IDS,
    omitted_input,
    read_json_input,
    render_codex_workcell_storage_operator_consent_verifier_markdown,
    verify_codex_workcell_storage_operator_consent_contract,
)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a metadata-only Codex workcell storage operator consent request contract JSON.")
    parser.add_argument("--storage-operator-consent-contract-json", required=True)
    parser.add_argument("--output", required=True)
    for input_id in OPTIONAL_INPUT_IDS:
        parser.add_argument("--" + input_id.replace("_", "-"), dest=input_id)
    parser.add_argument("--markdown-output")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    try:
        contract_summary, contract = read_json_input(args.storage_operator_consent_contract_json, "storage_operator_consent_contract_json")
        optional_summaries: dict[str, dict[str, object]] = {}
        optional_reports: dict[str, dict[str, object]] = {}
        for input_id in OPTIONAL_INPUT_IDS:
            path = getattr(args, input_id)
            if path:
                summary, report = read_json_input(path, input_id)
                optional_summaries[input_id] = summary; optional_reports[input_id] = report
            else:
                optional_summaries[input_id] = omitted_input(input_id)
        report = verify_codex_workcell_storage_operator_consent_contract(storage_operator_consent_contract=contract, storage_operator_consent_contract_summary=contract_summary, optional_reports=optional_reports, optional_summaries=optional_summaries)
    except CodexWorkcellStorageOperatorConsentVerifierError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    Path(args.output).write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if args.markdown_output:
        Path(args.markdown_output).write_text(render_codex_workcell_storage_operator_consent_verifier_markdown(report), encoding="utf-8")
    if args.summary:
        print(json.dumps({"storage_operator_consent_verifier_id": report["storage_operator_consent_verifier_id"], "verification_status": report["verification_status"], "violation_count": report["violation_summary"]["violation_count"], "warning_count": report["violation_summary"]["warning_count"]}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
