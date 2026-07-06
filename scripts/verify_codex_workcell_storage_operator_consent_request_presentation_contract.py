#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sentientos.codex_workcell_storage_operator_consent_request_presentation_verifier import (
    OPTIONAL_INPUT_IDS,
    CodexWorkcellStorageOperatorConsentRequestPresentationVerifierError,
    omitted_input,
    read_json_input,
    render_codex_workcell_storage_operator_consent_request_presentation_verifier_markdown,
    verify_codex_workcell_storage_operator_consent_request_presentation_contract,
)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a metadata-only Codex workcell storage operator consent request presentation contract JSON.")
    parser.add_argument("--storage-operator-consent-request-presentation-contract-json", dest="canonical_presentation_contract_json")
    parser.add_argument("--presentation-contract-json", dest="legacy_presentation_contract_json")
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output")
    parser.add_argument("--summary", action="store_true")
    for input_id in OPTIONAL_INPUT_IDS:
        parser.add_argument("--" + input_id.replace("_", "-"), dest=input_id)
    args = parser.parse_args(argv)
    try:
        contract_path = args.canonical_presentation_contract_json or args.legacy_presentation_contract_json
        if not contract_path:
            raise CodexWorkcellStorageOperatorConsentRequestPresentationVerifierError("missing_required_argument:--storage-operator-consent-request-presentation-contract-json")
        if args.canonical_presentation_contract_json and args.legacy_presentation_contract_json and args.canonical_presentation_contract_json != args.legacy_presentation_contract_json:
            raise CodexWorkcellStorageOperatorConsentRequestPresentationVerifierError("conflicting_presentation_contract_paths")
        contract_summary, contract = read_json_input(contract_path, "presentation_contract_json")
        optional_reports: dict[str, dict[str, object]] = {}
        optional_summaries: dict[str, dict[str, object]] = {}
        for input_id in OPTIONAL_INPUT_IDS:
            path = getattr(args, input_id)
            if path:
                summary, report = read_json_input(path, input_id)
                optional_summaries[input_id] = summary; optional_reports[input_id] = report
            else:
                optional_summaries[input_id] = omitted_input(input_id)
        report = verify_codex_workcell_storage_operator_consent_request_presentation_contract(contract=contract, contract_summary=contract_summary, optional_reports=optional_reports, optional_summaries=optional_summaries)
    except CodexWorkcellStorageOperatorConsentRequestPresentationVerifierError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    Path(args.output).write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if args.markdown_output:
        Path(args.markdown_output).write_text(render_codex_workcell_storage_operator_consent_request_presentation_verifier_markdown(report), encoding="utf-8")
    if args.summary:
        print(json.dumps({"storage_operator_consent_request_presentation_verifier_id": report["storage_operator_consent_request_presentation_verifier_id"], "verification_status": report["verification_status"], "violation_count": report["violation_summary"]["violation_count"]}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
