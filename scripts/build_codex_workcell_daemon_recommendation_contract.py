#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys

from sentientos.codex_workcell_daemon_recommendation_contract import (
    CodexWorkcellDaemonRecommendationContractError,
    CodexWorkcellDaemonRecommendationContractRequest,
    build_codex_workcell_daemon_recommendation_contract,
    render_codex_workcell_daemon_recommendation_contract_markdown,
    write_codex_workcell_daemon_recommendation_contract_json,
    write_codex_workcell_daemon_recommendation_contract_markdown,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a metadata-only Codex workcell daemon recommendation contract.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--pulse-contract-json")
    parser.add_argument("--health-snapshot-json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        contract = build_codex_workcell_daemon_recommendation_contract(CodexWorkcellDaemonRecommendationContractRequest(pulse_contract_json=args.pulse_contract_json, health_snapshot_json=args.health_snapshot_json))
    except CodexWorkcellDaemonRecommendationContractError as exc:
        print(f"codex_workcell_daemon_recommendation_contract_error: {exc}", file=sys.stderr)
        return 2
    write_codex_workcell_daemon_recommendation_contract_json(contract, args.output)
    if args.markdown_output:
        write_codex_workcell_daemon_recommendation_contract_markdown(render_codex_workcell_daemon_recommendation_contract_markdown(contract), args.markdown_output)
    if args.summary:
        print(json.dumps({"daemon_recommendation_contract_id": contract["daemon_recommendation_contract_id"], "metadata_only": True, "daemon_recommendation_contract_only": True, "output": args.output, "markdown_output": args.markdown_output, "pulse_contract_provided": contract["pulse_contract_input_summary"].get("provided"), "health_snapshot_provided": contract["health_snapshot_input_summary"].get("provided"), "recommendation_count": len(contract["recommendation_catalog"]), "applicable_recommendation_count": len(contract["observed_recommendation_summary"].get("applicable_recommendation_ids", []))}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
