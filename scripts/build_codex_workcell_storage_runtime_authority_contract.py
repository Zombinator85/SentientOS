#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sentientos.codex_workcell_storage_runtime_authority_contract import (
    CodexWorkcellStorageRuntimeAuthorityContractError,
    INPUT_SPECS,
    build_codex_workcell_storage_runtime_authority_contract,
    omitted_input,
    read_json_input,
    render_codex_workcell_storage_runtime_authority_contract_markdown,
)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a metadata-only Codex workcell storage runtime authority boundary contract.")
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
            if path:
                summary, _loaded = read_json_input(path, input_id)
                summaries[input_id] = summary
            else:
                summaries[input_id] = omitted_input(input_id)
        contract = build_codex_workcell_storage_runtime_authority_contract(input_summaries=summaries, commit_sha=args.commit_sha, pr_number=args.pr_number, pr_title=args.pr_title)
    except CodexWorkcellStorageRuntimeAuthorityContractError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    Path(args.output).write_text(json.dumps(contract, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if args.markdown_output:
        Path(args.markdown_output).write_text(render_codex_workcell_storage_runtime_authority_contract_markdown(contract), encoding="utf-8")
    if args.summary:
        print(json.dumps({"storage_runtime_authority_contract_id": contract["storage_runtime_authority_contract_id"], "supplied_report_count": contract["runtime_context"]["supplied_report_count"], "active_storage_allowed_now": contract["active_storage_allowed_now"], "runtime_binding_not_performed": contract["runtime_binding_not_performed"]}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
