#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys

from sentientos.codex_landing_evidence_appendix import (
    CodexLandingEvidenceAppendixError,
    CodexLandingEvidenceAppendixRequest,
    build_landing_evidence_appendix,
    write_landing_evidence_appendix,
    write_landing_evidence_appendix_metadata,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render existing Codex landing evidence as a non-authoritative markdown appendix.")
    parser.add_argument("--title", required=True)
    parser.add_argument("--intended-commit-title", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--evidence-index-json")
    parser.add_argument("--doctor-report-json")
    parser.add_argument("--doctrine-map-json")
    parser.add_argument("--json-output")
    parser.add_argument("--summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    request = CodexLandingEvidenceAppendixRequest(
        title=args.title,
        intended_commit_title=args.intended_commit_title,
        output=args.output,
        evidence_index_json=args.evidence_index_json,
        doctor_report_json=args.doctor_report_json,
        json_output=args.json_output,
        doctrine_map_json=args.doctrine_map_json,
    )
    try:
        markdown, metadata = build_landing_evidence_appendix(request)
    except CodexLandingEvidenceAppendixError as exc:
        print(f"codex_landing_evidence_appendix_error: {exc}", file=sys.stderr)
        return 2
    write_landing_evidence_appendix(markdown, args.output)
    if args.json_output:
        write_landing_evidence_appendix_metadata(metadata, args.json_output)
    if args.summary:
        print(json.dumps({"appendix_is_non_authoritative": True, "doctor_report_provided": metadata["doctor_report_provided"], "evidence_index_provided": metadata["evidence_index_provided"], "doctrine_map_provided": metadata["doctrine_map_json_path"] is not None, "doctrine_trait_count": metadata["doctrine_trait_count"], "doctrine_rail_mapping_count": metadata["doctrine_rail_mapping_count"], "output": args.output}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
