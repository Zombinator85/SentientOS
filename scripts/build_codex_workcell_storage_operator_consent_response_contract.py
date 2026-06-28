#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sentientos.codex_workcell_storage_operator_consent_response_contract import (
    CodexWorkcellStorageOperatorConsentResponseContractError,
    INPUT_SPECS,
    build_codex_workcell_storage_operator_consent_response_contract,
    omitted_input,
    read_json_input,
    render_codex_workcell_storage_operator_consent_response_contract_markdown,
)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a metadata-only Codex workcell storage operator consent response artifact contract.")
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
        contract = build_codex_workcell_storage_operator_consent_response_contract(input_summaries=summaries, input_reports=reports, commit_sha=args.commit_sha, pr_number=args.pr_number, pr_title=args.pr_title)
    except CodexWorkcellStorageOperatorConsentResponseContractError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    Path(args.output).write_text(json.dumps(contract, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if args.markdown_output:
        Path(args.markdown_output).write_text(render_codex_workcell_storage_operator_consent_response_contract_markdown(contract), encoding="utf-8")
    if args.summary:
        print(json.dumps({"storage_operator_consent_response_contract_id": contract["storage_operator_consent_response_contract_id"], "supplied_report_count": contract["response_contract_context"]["supplied_report_count"], "response_artifact_not_created": contract["response_artifact_not_created"], "active_storage_allowed_now": contract["active_storage_allowed_now"]}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
