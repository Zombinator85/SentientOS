#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sentientos.codex_workcell_storage_operator_consent_response_verifier import (
    OPTIONAL_INPUT_IDS,
    REQUIRED_CONTRACT_INPUT_ID,
    CodexWorkcellStorageOperatorConsentResponseVerifierError,
    omitted_input,
    read_json_input,
    render_codex_workcell_storage_operator_consent_response_verifier_markdown,
    verify_codex_workcell_storage_operator_consent_response_contract,
)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a metadata-only Codex workcell storage operator consent response artifact contract.")
    parser.add_argument("--storage-operator-consent-response-contract-json", dest=REQUIRED_CONTRACT_INPUT_ID, required=True)
    parser.add_argument("--output", required=True)
    for input_id in OPTIONAL_INPUT_IDS:
        parser.add_argument("--" + input_id.replace("_", "-"), dest=input_id)
    parser.add_argument("--markdown-output")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    summaries: dict[str, dict[str, object]] = {}
    reports: dict[str, dict[str, object]] = {}
    try:
        summaries[REQUIRED_CONTRACT_INPUT_ID], response_contract = read_json_input(getattr(args, REQUIRED_CONTRACT_INPUT_ID), REQUIRED_CONTRACT_INPUT_ID)
        for input_id in OPTIONAL_INPUT_IDS:
            path = getattr(args, input_id)
            if path:
                summaries[input_id], reports[input_id] = read_json_input(path, input_id)
            else:
                summaries[input_id] = omitted_input(input_id)
        report = verify_codex_workcell_storage_operator_consent_response_contract(response_contract=response_contract, input_summaries=summaries, optional_reports=reports)
    except CodexWorkcellStorageOperatorConsentResponseVerifierError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    Path(args.output).write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if args.markdown_output:
        Path(args.markdown_output).write_text(render_codex_workcell_storage_operator_consent_response_verifier_markdown(report), encoding="utf-8")
    if args.summary:
        print(json.dumps({"storage_operator_consent_response_verifier_id": report["storage_operator_consent_response_verifier_id"], "verification_status": report["verification_status"], "violation_count": report["violation_summary"]["violation_count"], "response_artifact_not_created": report["response_artifact_not_created"], "active_storage_allowed_now": report["active_storage_allowed_now"]}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
