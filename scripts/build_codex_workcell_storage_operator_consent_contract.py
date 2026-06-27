#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sentientos.codex_workcell_storage_operator_consent_contract import (
    CodexWorkcellStorageOperatorConsentContractError,
    INPUT_SPECS,
    build_codex_workcell_storage_operator_consent_contract,
    omitted_input,
    read_json_input,
    render_codex_workcell_storage_operator_consent_contract_markdown,
)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a metadata-only Codex workcell storage operator consent request contract.")
    parser.add_argument("--output", required=True)
    for input_id in INPUT_SPECS:
        parser.add_argument("--" + input_id.replace("_", "-"), dest=input_id)
    parser.add_argument("--commit-sha")
    parser.add_argument("--pr-number")
    parser.add_argument("--pr-title")
    parser.add_argument("--markdown-output")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    summaries = {}
    try:
        for input_id in INPUT_SPECS:
            path = getattr(args, input_id)
            summaries[input_id] = read_json_input(path, input_id)[0] if path else omitted_input(input_id)
        contract = build_codex_workcell_storage_operator_consent_contract(input_summaries=summaries, commit_sha=args.commit_sha, pr_number=args.pr_number, pr_title=args.pr_title)
    except CodexWorkcellStorageOperatorConsentContractError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    Path(args.output).write_text(json.dumps(contract, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if args.markdown_output:
        Path(args.markdown_output).write_text(render_codex_workcell_storage_operator_consent_contract_markdown(contract), encoding="utf-8")
    if args.summary:
        print(json.dumps({"storage_operator_consent_contract_id": contract["storage_operator_consent_contract_id"], "supplied_report_count": contract["consent_context"]["supplied_report_count"], "consent_not_collected": contract["consent_not_collected"], "active_storage_allowed_now": contract["active_storage_allowed_now"]}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
