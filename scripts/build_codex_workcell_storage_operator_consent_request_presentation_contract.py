#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sentientos.codex_workcell_storage_operator_consent_request_presentation_contract import (
    CodexWorkcellStorageOperatorConsentRequestPresentationContractError,
    INPUT_SPECS,
    build_codex_workcell_storage_operator_consent_request_presentation_contract,
    omitted_input,
    read_json_input,
    render_codex_workcell_storage_operator_consent_request_presentation_contract_markdown,
)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a metadata-only Codex workcell storage operator consent request presentation boundary contract.")
    parser.add_argument("--output", required=True)
    for input_id in INPUT_SPECS:
        parser.add_argument("--" + input_id.replace("_", "-"), dest=input_id)
    parser.add_argument("--commit")
    parser.add_argument("--pr")
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
        contract = build_codex_workcell_storage_operator_consent_request_presentation_contract(input_summaries=summaries, input_reports=reports, commit=args.commit, pr=args.pr)
    except CodexWorkcellStorageOperatorConsentRequestPresentationContractError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    Path(args.output).write_text(json.dumps(contract, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if args.markdown_output:
        Path(args.markdown_output).write_text(render_codex_workcell_storage_operator_consent_request_presentation_contract_markdown(contract), encoding="utf-8")
    if args.summary:
        print(json.dumps({"storage_operator_consent_request_presentation_contract_id": contract["storage_operator_consent_request_presentation_contract_id"], "supplied_input_count": contract["presentation_boundary_context"]["supplied_input_count"], "presentation_not_performed": contract["presentation_not_performed"], "active_storage_allowed_now": contract["active_storage_allowed_now"]}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
