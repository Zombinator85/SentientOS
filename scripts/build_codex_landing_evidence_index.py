#!/usr/bin/env python
from __future__ import annotations

import argparse
import json

from sentientos.codex_landing_evidence_index import CodexLandingEvidenceIndexRequest, build_landing_evidence_index, write_landing_evidence_index


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a metadata-only Codex landing evidence index without granting authority.")
    parser.add_argument("--title", required=True)
    parser.add_argument("--intended-commit-title", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--matrix-json-path")
    parser.add_argument("--pre-commit-finalizer-json")
    parser.add_argument("--pr-metadata-finalizer-json")
    parser.add_argument("--pr-metadata-guard-json")
    parser.add_argument("--lifecycle-summary-json")
    parser.add_argument("--doctor-report-json")
    parser.add_argument("--test-provenance-json")
    parser.add_argument("--summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    index = build_landing_evidence_index(
        CodexLandingEvidenceIndexRequest(
            title=args.title,
            intended_commit_title=args.intended_commit_title,
            output=args.output,
            matrix_json_path=args.matrix_json_path,
            pre_commit_finalizer_json=args.pre_commit_finalizer_json,
            pr_metadata_finalizer_json=args.pr_metadata_finalizer_json,
            pr_metadata_guard_json=args.pr_metadata_guard_json,
            lifecycle_summary_json=args.lifecycle_summary_json,
            doctor_report_json=args.doctor_report_json,
            test_provenance_json=args.test_provenance_json,
        )
    )
    write_landing_evidence_index(index, args.output)
    if args.summary:
        print(json.dumps({"evidence_index_id": index["evidence_index_id"], "artifact_count": index["artifact_count"], "artifact_roles_missing": index["artifact_roles_missing"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
