#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys

from sentientos.codex_workcell_storage_policy_contract import (
    CodexWorkcellStoragePolicyContractError,
    INPUT_IDS,
    build_codex_workcell_storage_policy_contract,
    read_json_input,
    render_codex_workcell_storage_policy_contract_markdown,
    write_codex_workcell_storage_policy_contract_json,
    write_codex_workcell_storage_policy_contract_markdown,
)

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a metadata-only Codex workcell storage policy contract.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--vow-boundary-contract-json")
    parser.add_argument("--vow-alignment-attestation-json")
    parser.add_argument("--memory-contract-json")
    parser.add_argument("--memory-activation-preflight-json")
    parser.add_argument("--markdown-output")
    parser.add_argument("--summary", action="store_true")
    return parser

def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        inputs = {input_id: read_json_input(getattr(args, input_id), input_id) for input_id in INPUT_IDS}
        report = build_codex_workcell_storage_policy_contract(inputs)
    except CodexWorkcellStoragePolicyContractError as exc:
        print(f"codex_workcell_storage_policy_contract_error: {exc}", file=sys.stderr)
        return 2
    write_codex_workcell_storage_policy_contract_json(report, args.output)
    if args.markdown_output:
        write_codex_workcell_storage_policy_contract_markdown(render_codex_workcell_storage_policy_contract_markdown(report), args.markdown_output)
    if args.summary:
        print(json.dumps({"storage_policy_contract_id": report["storage_policy_contract_id"], "metadata_only": True, "storage_policy_contract_only": True, "active_storage_allowed_now": report["storage_activation_gap_summary"]["active_storage_allowed_now"], "output": args.output, "markdown_output": args.markdown_output}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
