from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.work_item_lifecycle_attestation_review_digest_index_verifier import (
    PASS_STATUSES,
    WorkItemLifecycleAttestationReviewDigestIndexVerificationPolicy,
    WorkItemLifecycleAttestationReviewDigestIndexVerificationRequest,
    evaluate_work_item_lifecycle_attestation_review_digest_index_verification,
    write_work_item_lifecycle_attestation_review_digest_index_verification_report,
)


def _load(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--review-digest-index", type=Path, required=True)
    p.add_argument("--review-digest", type=Path, action="append", default=[])
    p.add_argument("--review-digest-verification", type=Path, action="append", default=[])
    p.add_argument("--matrix-report", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--summary", action="store_true")
    p.add_argument("--require-matrix", action="store_true")
    p.add_argument("--require-source-digests", action="store_true")
    p.add_argument("--require-verifier-reports", action="store_true")
    p.add_argument("--allow-warning-index", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--allow-attention-index-review", action=argparse.BooleanOptionalAction, default=False)
    args = p.parse_args(argv)

    req = WorkItemLifecycleAttestationReviewDigestIndexVerificationRequest(
        review_digest_index=_load(args.review_digest_index),
        review_digests=tuple((str(x), _load(x)) for x in args.review_digest),
        review_digest_verifier_reports=tuple((str(x), _load(x)) for x in args.review_digest_verification),
        matrix_report=_load(args.matrix_report) if args.matrix_report else None,
    )
    policy = WorkItemLifecycleAttestationReviewDigestIndexVerificationPolicy(
        allow_warning_index=args.allow_warning_index,
        allow_attention_index_review=args.allow_attention_index_review,
        source_digests_required=args.require_source_digests,
        verifier_reports_required=args.require_verifier_reports,
        matrix_required=args.require_matrix,
    )
    result = evaluate_work_item_lifecycle_attestation_review_digest_index_verification(req, policy=policy)

    if args.output:
        write_work_item_lifecycle_attestation_review_digest_index_verification_report(result, args.output)
    if args.summary:
        r = result.report
        print(f"verification_status={result.status}")
        print(f"review_digest_index_id={r.review_digest_index_id}")
        print(f"finding_count={r.finding_count}")
        print(f"report_digest={r.review_digest_index_verification_report_digest}")
    else:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.status in PASS_STATUSES else 1


if __name__ == "__main__":
    raise SystemExit(main())
