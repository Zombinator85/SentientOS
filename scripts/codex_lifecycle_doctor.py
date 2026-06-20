#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys

from sentientos.codex_lifecycle_doctor import (
    CodexLifecycleDoctorError,
    CodexLifecycleDoctorRequest,
    build_lifecycle_doctor_report,
    write_lifecycle_doctor_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect existing Codex landing artifacts without granting authority.")
    parser.add_argument("--title", required=True)
    parser.add_argument("--intended-commit-title", required=True)
    parser.add_argument("--matrix-json-path")
    parser.add_argument("--evidence-index-json")
    parser.add_argument("--pre-commit-finalizer-json")
    parser.add_argument("--pr-metadata-finalizer-json")
    parser.add_argument("--pr-metadata-guard-json")
    parser.add_argument("--lifecycle-summary-json")
    parser.add_argument("--test-provenance-json")
    parser.add_argument("--output")
    parser.add_argument("--summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = build_lifecycle_doctor_report(
            CodexLifecycleDoctorRequest(
                title=args.title,
                intended_commit_title=args.intended_commit_title,
                matrix_json_path=args.matrix_json_path,
                pre_commit_finalizer_json=args.pre_commit_finalizer_json,
                pr_metadata_finalizer_json=args.pr_metadata_finalizer_json,
                pr_metadata_guard_json=args.pr_metadata_guard_json,
                lifecycle_summary_json=args.lifecycle_summary_json,
                test_provenance_json=args.test_provenance_json,
                evidence_index_json=args.evidence_index_json,
                output=args.output,
            )
        )
    except CodexLifecycleDoctorError as exc:
        print(f"codex_lifecycle_doctor_error: {exc}", file=sys.stderr)
        return 2
    if args.output:
        write_lifecycle_doctor_report(report, args.output)
    if args.summary:
        summary = {"doctor_report_id": report["doctor_report_id"], "overall_doctor_status": report["overall_doctor_status"], "next_safe_action": report["next_safe_action"]}
        if args.evidence_index_json:
            summary["evidence_index_intake"] = "supplied"
            summary["evidence_index_used_roles"] = report.get("evidence_index_used_roles", [])
        print(json.dumps(summary, sort_keys=True))
    elif not args.output:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
