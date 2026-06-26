#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sentientos.codex_workcell_storage_transaction_plan import (
    CodexWorkcellStorageTransactionPlanError,
    build_codex_workcell_storage_transaction_plan,
    read_json_input,
    render_codex_workcell_storage_transaction_plan_markdown,
)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a metadata-only Codex workcell storage transaction dry-run plan.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--storage-policy-contract-json", required=True)
    parser.add_argument("--storage-policy-verifier-json", required=True)
    parser.add_argument("--memory-candidate-bundle-json", required=True)
    parser.add_argument("--memory-candidate-verifier-json", required=True)
    parser.add_argument("--vow-boundary-contract-json", required=True)
    parser.add_argument("--vow-alignment-attestation-json", required=True)
    parser.add_argument("--commit-sha")
    parser.add_argument("--pr-number")
    parser.add_argument("--pr-title")
    parser.add_argument("--canonical-vow-digest")
    parser.add_argument("--markdown-output")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    try:
        inputs = {}
        data = {}
        for attr, input_id in (
            ("storage_policy_contract_json", "storage_policy_contract_json"), ("storage_policy_verifier_json", "storage_policy_verifier_json"),
            ("memory_candidate_bundle_json", "memory_candidate_bundle_json"), ("memory_candidate_verifier_json", "memory_candidate_verifier_json"),
            ("vow_boundary_contract_json", "vow_boundary_contract_json"), ("vow_alignment_attestation_json", "vow_alignment_attestation_json"),
        ):
            summary, loaded = read_json_input(getattr(args, attr), input_id)
            inputs[input_id] = summary
            data[input_id] = loaded
        plan = build_codex_workcell_storage_transaction_plan(
            storage_policy_contract=data["storage_policy_contract_json"], storage_policy_verifier=data["storage_policy_verifier_json"],
            memory_candidate_bundle=data["memory_candidate_bundle_json"], memory_candidate_verifier=data["memory_candidate_verifier_json"],
            vow_boundary_contract=data["vow_boundary_contract_json"], vow_alignment_attestation=data["vow_alignment_attestation_json"], input_summaries=inputs,
            commit_sha=args.commit_sha, pr_number=args.pr_number, pr_title=args.pr_title, canonical_vow_digest=args.canonical_vow_digest,
        )
    except CodexWorkcellStorageTransactionPlanError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    Path(args.output).write_text(json.dumps(plan, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if args.markdown_output:
        Path(args.markdown_output).write_text(render_codex_workcell_storage_transaction_plan_markdown(plan), encoding="utf-8")
    if args.summary:
        print(json.dumps({"storage_transaction_plan_id": plan["storage_transaction_plan_id"], "planned_ledger_transaction_count": len(plan["ledger_transaction_plan"]), "planned_glow_transaction_count": len(plan["glow_transaction_plan"]), "blocking_gap_count": plan["transaction_gap_summary"]["blocking_gap_count"], "active_storage_allowed_now": plan["transaction_gap_summary"]["active_storage_allowed_now"]}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
