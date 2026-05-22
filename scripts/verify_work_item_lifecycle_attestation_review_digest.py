from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

from sentientos.work_item_lifecycle_attestation_review_digest_verifier import PASS_STATUSES, WorkItemLifecycleAttestationReviewDigestVerificationPolicy, WorkItemLifecycleAttestationReviewDigestVerificationRequest, evaluate_work_item_lifecycle_attestation_review_digest_verification, write_work_item_lifecycle_attestation_review_digest_verification_report


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-digest", required=True, type=Path)
    parser.add_argument("--attestation-index", required=True, type=Path)
    parser.add_argument("--index-verification", required=True, type=Path)
    parser.add_argument("--matrix-report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--require-matrix", action="store_true")
    parser.add_argument("--allow-warnings", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--allow-blockers-for-review", action="store_true")
    args = parser.parse_args(argv)

    result = evaluate_work_item_lifecycle_attestation_review_digest_verification(
        WorkItemLifecycleAttestationReviewDigestVerificationRequest(
            review_digest=_load(args.review_digest),
            attestation_index=_load(args.attestation_index),
            index_verification_report=_load(args.index_verification),
            matrix_report=_load(args.matrix_report) if args.matrix_report else None,
        ),
        policy=WorkItemLifecycleAttestationReviewDigestVerificationPolicy(
            allow_warnings=args.allow_warnings,
            allow_blockers_for_review=args.allow_blockers_for_review,
            matrix_required=args.require_matrix,
        ),
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if args.output:
        write_work_item_lifecycle_attestation_review_digest_verification_report(result, args.output)
    if args.summary:
        print(f"status={result.status} digest_id={result.report.review_digest_id} finding_count={result.report.finding_count} report_digest={result.report.review_digest_verification_report_digest}")
    return 0 if result.status in PASS_STATUSES else 1


if __name__ == "__main__":
    raise SystemExit(main())
