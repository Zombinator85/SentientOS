from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

from sentientos.work_item_lifecycle_attestation_review_digest_index import (
    SUCCESS_STATUSES,
    WorkItemLifecycleAttestationReviewDigestIndexPolicy,
    WorkItemLifecycleAttestationReviewDigestIndexRequest,
    build_work_item_lifecycle_attestation_review_digest_index,
    write_work_item_lifecycle_attestation_review_digest_index,
)


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--review-digest", action="append", required=True, type=Path)
    p.add_argument("--review-digest-verification", action="append", default=[], type=Path)
    p.add_argument("--matrix-report", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--summary", action="store_true")
    p.add_argument("--require-matrix", action="store_true")
    p.add_argument("--require-clear", action="store_true")
    p.add_argument("--require-verifier-reports", action="store_true")
    p.add_argument("--allow-skipped-inputs", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--allow-duplicate-digests", action=argparse.BooleanOptionalAction, default=False)
    args = p.parse_args(argv)

    result = build_work_item_lifecycle_attestation_review_digest_index(
        WorkItemLifecycleAttestationReviewDigestIndexRequest(
            review_digests=tuple(_load(path) for path in args.review_digest),
            review_digest_verifier_reports=tuple(_load(path) for path in args.review_digest_verification),
            matrix_report=_load(args.matrix_report) if args.matrix_report else None,
        ),
        policy=WorkItemLifecycleAttestationReviewDigestIndexPolicy(
            allow_skipped_inputs=args.allow_skipped_inputs,
            allow_duplicate_digests=args.allow_duplicate_digests,
            require_clear=args.require_clear,
            require_verifier_reports=args.require_verifier_reports,
            matrix_required=args.require_matrix,
        ),
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if args.output:
        write_work_item_lifecycle_attestation_review_digest_index(result, args.output)
    if args.summary:
        i = result.index
        print(
            f"status={result.status} aggregate_reviewer_posture={i.aggregate_reviewer_posture} indexed_count={i.indexed_count} attention_count={sum(1 for e in i.entries if e.attention_required)} digest={i.review_digest_index_digest}"
        )
    return 0 if result.status in SUCCESS_STATUSES else 1


if __name__ == "__main__":
    raise SystemExit(main())
