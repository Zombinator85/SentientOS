#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys

from sentientos.codex_workcell_vow_alignment_attestation import (
    CodexWorkcellVowAlignmentAttestationError,
    INPUT_IDS,
    build_codex_workcell_vow_alignment_attestation,
    read_json_input,
    render_codex_workcell_vow_alignment_attestation_markdown,
    write_codex_workcell_vow_alignment_attestation_json,
    write_codex_workcell_vow_alignment_attestation_markdown,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a metadata-only Codex workcell vow alignment attestation bundle.")
    parser.add_argument("--vow-boundary-contract-json", required=True)
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
        vow_summary, vow_data = read_json_input(args.vow_boundary_contract_json, "vow_boundary_contract_json", required=True)
        if vow_data is None:
            raise CodexWorkcellVowAlignmentAttestationError("missing_required_vow_boundary_contract_json")
        inputs = {input_id: read_json_input(getattr(args, input_id), input_id) for input_id in INPUT_IDS}
        report = build_codex_workcell_vow_alignment_attestation((vow_summary, vow_data), inputs)
    except CodexWorkcellVowAlignmentAttestationError as exc:
        print(f"codex_workcell_vow_alignment_attestation_error: {exc}", file=sys.stderr)
        return 2
    write_codex_workcell_vow_alignment_attestation_json(report, args.output)
    if args.markdown_output:
        write_codex_workcell_vow_alignment_attestation_markdown(render_codex_workcell_vow_alignment_attestation_markdown(report), args.markdown_output)
    if args.summary:
        print(json.dumps({"vow_alignment_attestation_id": report["vow_alignment_attestation_id"], "metadata_only": True, "attestation_bundle_only": True, "canonical_vow_digest": report["canonical_vow_digest"], "supplied_report_count": report["constraint_coverage_summary"]["supplied_report_count"], "failed_attestation_count": report["attestation_gap_summary"]["failed_attestation_count"], "output": args.output, "markdown_output": args.markdown_output}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
