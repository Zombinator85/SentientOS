#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sentientos.codex_workcell_storage_transaction_plan_verifier import (
    CodexWorkcellStorageTransactionPlanVerifierError,
    omitted_input,
    read_json_input,
    render_codex_workcell_storage_transaction_plan_verifier_markdown,
    verify_codex_workcell_storage_transaction_plan,
)

def main() -> int:
    parser=argparse.ArgumentParser(description="Verify a Codex workcell storage transaction plan JSON.")
    parser.add_argument("--storage-transaction-plan-json", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--storage-policy-contract-json")
    parser.add_argument("--storage-policy-verifier-json")
    parser.add_argument("--markdown-output")
    parser.add_argument("--summary", action="store_true")
    args=parser.parse_args()
    try:
        plan_summary, plan = read_json_input(args.storage_transaction_plan_json, "storage_transaction_plan")
        contract_summary, contract = (read_json_input(args.storage_policy_contract_json, "storage_policy_contract") if args.storage_policy_contract_json else (omitted_input("storage_policy_contract"), None))
        verifier_summary, verifier = (read_json_input(args.storage_policy_verifier_json, "storage_policy_verifier") if args.storage_policy_verifier_json else (omitted_input("storage_policy_verifier"), None))
    except CodexWorkcellStorageTransactionPlanVerifierError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    report=verify_codex_workcell_storage_transaction_plan(storage_transaction_plan=plan, storage_transaction_plan_summary=plan_summary, storage_policy_contract=contract, storage_policy_contract_summary=contract_summary, storage_policy_verifier=verifier, storage_policy_verifier_summary=verifier_summary)
    Path(args.output).write_text(json.dumps(report, sort_keys=True, indent=2)+"\n", encoding="utf-8")
    if args.markdown_output:
        Path(args.markdown_output).write_text(render_codex_workcell_storage_transaction_plan_verifier_markdown(report), encoding="utf-8")
    if args.summary:
        print(json.dumps({"storage_transaction_plan_verifier_id": report["storage_transaction_plan_verifier_id"], "verification_status": report["verification_status"], "violation_count": report["violation_summary"]["violation_count"], "warning_count": report["violation_summary"]["warning_count"]}, sort_keys=True))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
