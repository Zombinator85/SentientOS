#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys

from sentientos.codex_workcell_memory_candidate_verifier import (
    CodexWorkcellMemoryCandidateVerifierError,
    read_json_input,
    render_codex_workcell_memory_candidate_verifier_markdown,
    verify_codex_workcell_memory_candidate_bundle,
    write_codex_workcell_memory_candidate_verifier_json,
    write_codex_workcell_memory_candidate_verifier_markdown,
)

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify a metadata-only Codex workcell memory candidate bundle.")
    parser.add_argument("--candidate-bundle-json", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--memory-contract-json")
    parser.add_argument("--markdown-output")
    parser.add_argument("--summary", action="store_true")
    return parser

def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        candidate_summary, candidate = read_json_input(args.candidate_bundle_json, "candidate_bundle_json", required=True)
        if candidate is None:
            raise CodexWorkcellMemoryCandidateVerifierError("missing_candidate_bundle_json")
        contract_summary, contract = read_json_input(args.memory_contract_json, "memory_contract_json", required=False)
        report = verify_codex_workcell_memory_candidate_bundle(candidate, candidate_summary, contract, contract_summary)
    except CodexWorkcellMemoryCandidateVerifierError as exc:
        print(f"codex_workcell_memory_candidate_verifier_error: {exc}", file=sys.stderr)
        return 2
    write_codex_workcell_memory_candidate_verifier_json(report, args.output)
    if args.markdown_output:
        write_codex_workcell_memory_candidate_verifier_markdown(render_codex_workcell_memory_candidate_verifier_markdown(report), args.markdown_output)
    if args.summary:
        print(json.dumps({"memory_candidate_verifier_id": report["memory_candidate_verifier_id"], "metadata_only": True, "verifier_only": True, "verification_status": report["verification_status"], "violation_count": report["violation_summary"]["violation_count"], "warning_count": report["violation_summary"]["warning_count"], "output": args.output, "markdown_output": args.markdown_output}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
