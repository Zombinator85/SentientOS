#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys

from sentientos.codex_workcell_memory_contract import (
    CodexWorkcellMemoryContractError,
    CodexWorkcellMemoryContractRequest,
    build_codex_workcell_memory_contract,
    render_codex_workcell_memory_contract_markdown,
    write_codex_workcell_memory_contract_json,
    write_codex_workcell_memory_contract_markdown,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a metadata-only Codex workcell memory contract.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--health-snapshot-json")
    parser.add_argument("--pulse-contract-json")
    parser.add_argument("--daemon-recommendation-contract-json")
    parser.add_argument("--evidence-index-json")
    parser.add_argument("--appendix-sidecar-json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        contract = build_codex_workcell_memory_contract(
            CodexWorkcellMemoryContractRequest(
                health_snapshot_json=args.health_snapshot_json,
                pulse_contract_json=args.pulse_contract_json,
                daemon_recommendation_contract_json=args.daemon_recommendation_contract_json,
                evidence_index_json=args.evidence_index_json,
                appendix_sidecar_json=args.appendix_sidecar_json,
            )
        )
    except CodexWorkcellMemoryContractError as exc:
        print(f"codex_workcell_memory_contract_error: {exc}", file=sys.stderr)
        return 2
    write_codex_workcell_memory_contract_json(contract, args.output)
    if args.markdown_output:
        write_codex_workcell_memory_contract_markdown(render_codex_workcell_memory_contract_markdown(contract), args.markdown_output)
    if args.summary:
        print(json.dumps({"workcell_memory_contract_id": contract["workcell_memory_contract_id"], "metadata_only": True, "memory_contract_only": True, "output": args.output, "markdown_output": args.markdown_output, "ledger_record_type_count": len(contract["ledger_record_type_index"]), "glow_archive_item_type_count": len(contract["glow_archive_item_type_index"]), "provided_input_count": sum(1 for item in contract["input_summaries"].values() if item.get("provided"))}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
