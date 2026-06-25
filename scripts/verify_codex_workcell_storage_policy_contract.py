#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

from sentientos.codex_workcell_storage_policy_verifier import (
    CodexWorkcellStoragePolicyVerifierError,
    build_verification_from_paths,
    render_codex_workcell_storage_policy_verifier_markdown,
    write_json,
    write_markdown,
)

def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Codex workcell storage policy contract metadata.")
    parser.add_argument("--storage-policy-contract-json", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--vow-boundary-contract-json")
    parser.add_argument("--vow-alignment-attestation-json")
    parser.add_argument("--memory-contract-json")
    parser.add_argument("--memory-activation-preflight-json")
    parser.add_argument("--markdown-output")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    try:
        report = build_verification_from_paths(
            args.storage_policy_contract_json,
            vow_boundary_contract_json=args.vow_boundary_contract_json,
            vow_alignment_attestation_json=args.vow_alignment_attestation_json,
            memory_contract_json=args.memory_contract_json,
            memory_activation_preflight_json=args.memory_activation_preflight_json,
        )
    except CodexWorkcellStoragePolicyVerifierError as exc:
        print(f"storage_policy_verifier_input_error: {exc}", file=sys.stderr)
        return 2
    write_json(report, args.output)
    if args.markdown_output:
        write_markdown(render_codex_workcell_storage_policy_verifier_markdown(report), args.markdown_output)
    if args.summary:
        print(json.dumps({"verification_status": report["verification_status"], "violation_count": report["violation_summary"]["violation_count"], "output": args.output, "markdown_output": args.markdown_output}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
