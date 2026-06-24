#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys

from sentientos.codex_workcell_memory_activation_preflight import (
    CodexWorkcellMemoryActivationPreflightError,
    build_codex_workcell_memory_activation_preflight,
    read_json_input,
    render_codex_workcell_memory_activation_preflight_markdown,
    write_codex_workcell_memory_activation_preflight_json,
    write_codex_workcell_memory_activation_preflight_markdown,
)

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a metadata-only Codex workcell memory activation preflight report.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--memory-contract-json")
    parser.add_argument("--candidate-bundle-json")
    parser.add_argument("--candidate-verifier-json")
    parser.add_argument("--markdown-output")
    parser.add_argument("--summary", action="store_true")
    return parser

def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        contract_summary, contract = read_json_input(args.memory_contract_json, "memory_contract_json")
        bundle_summary, bundle = read_json_input(args.candidate_bundle_json, "candidate_bundle_json")
        verifier_summary, verifier = read_json_input(args.candidate_verifier_json, "candidate_verifier_json")
        report = build_codex_workcell_memory_activation_preflight(contract, contract_summary, bundle, bundle_summary, verifier, verifier_summary)
    except CodexWorkcellMemoryActivationPreflightError as exc:
        print(f"codex_workcell_memory_activation_preflight_error: {exc}", file=sys.stderr)
        return 2
    write_codex_workcell_memory_activation_preflight_json(report, args.output)
    if args.markdown_output:
        write_codex_workcell_memory_activation_preflight_markdown(render_codex_workcell_memory_activation_preflight_markdown(report), args.markdown_output)
    if args.summary:
        print(json.dumps({"memory_activation_preflight_id": report["memory_activation_preflight_id"], "metadata_only": True, "preflight_only": True, "activation_preflight_status": report["activation_preflight_status"], "blocking_gap_count": report["activation_gap_summary"]["blocking_gap_count"], "output": args.output, "markdown_output": args.markdown_output}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
