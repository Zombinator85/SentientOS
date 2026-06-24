#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys

from sentientos.codex_workcell_vow_boundary_contract import (
    CodexWorkcellVowBoundaryContractError,
    INPUT_IDS,
    build_codex_workcell_vow_boundary_contract,
    read_json_input,
    render_codex_workcell_vow_boundary_contract_markdown,
    write_codex_workcell_vow_boundary_contract_json,
    write_codex_workcell_vow_boundary_contract_markdown,
)

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a metadata-only Codex workcell vow digest boundary contract.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--architecture-json")
    parser.add_argument("--health-snapshot-json")
    parser.add_argument("--pulse-contract-json")
    parser.add_argument("--daemon-recommendation-contract-json")
    parser.add_argument("--memory-contract-json")
    parser.add_argument("--memory-candidate-bundle-json")
    parser.add_argument("--memory-candidate-verifier-json")
    parser.add_argument("--memory-activation-preflight-json")
    parser.add_argument("--markdown-output")
    parser.add_argument("--summary", action="store_true")
    return parser

def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        inputs = {}
        for input_id in INPUT_IDS:
            path = getattr(args, input_id)
            inputs[input_id] = read_json_input(path, input_id)
        report = build_codex_workcell_vow_boundary_contract(inputs)
    except CodexWorkcellVowBoundaryContractError as exc:
        print(f"codex_workcell_vow_boundary_contract_error: {exc}", file=sys.stderr)
        return 2
    write_codex_workcell_vow_boundary_contract_json(report, args.output)
    if args.markdown_output:
        write_codex_workcell_vow_boundary_contract_markdown(render_codex_workcell_vow_boundary_contract_markdown(report), args.markdown_output)
    if args.summary:
        print(json.dumps({"vow_boundary_contract_id": report["vow_boundary_contract_id"], "metadata_only": True, "vow_boundary_contract_only": True, "canonical_vow_digest": report["canonical_vow_digest"], "supplied_report_count": report["vow_gap_summary"]["supplied_report_count"], "failed_report_count": report["vow_gap_summary"]["failed_report_count"], "output": args.output, "markdown_output": args.markdown_output}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
