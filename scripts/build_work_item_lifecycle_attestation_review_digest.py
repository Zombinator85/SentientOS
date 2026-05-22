from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

from sentientos.work_item_lifecycle_attestation_review_digest import SUCCESS_STATUSES, WorkItemLifecycleAttestationReviewDigestPolicy, WorkItemLifecycleAttestationReviewDigestRequest, evaluate_work_item_lifecycle_attestation_review_digest, write_work_item_lifecycle_attestation_review_digest


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--attestation-index", required=True, type=Path)
    p.add_argument("--index-verification", required=True, type=Path)
    p.add_argument("--matrix-report", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--summary", action="store_true")
    p.add_argument("--require-matrix", action="store_true")
    p.add_argument("--require-no-attention-items", action="store_true")
    p.add_argument("--allow-warnings", action=argparse.BooleanOptionalAction, default=False)
    args = p.parse_args(argv)

    result = evaluate_work_item_lifecycle_attestation_review_digest(
        WorkItemLifecycleAttestationReviewDigestRequest(
            attestation_index=_load(args.attestation_index),
            index_verification_report=_load(args.index_verification),
            matrix_report=_load(args.matrix_report) if args.matrix_report else None,
        ),
        policy=WorkItemLifecycleAttestationReviewDigestPolicy(
            allow_warnings=args.allow_warnings,
            require_no_attention_items=args.require_no_attention_items,
            matrix_required=args.require_matrix,
        ),
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if args.output:
        write_work_item_lifecycle_attestation_review_digest(result, args.output)
    if args.summary:
        d = result.digest
        print(
            "status="
            f"{result.status} reviewer_posture={d.reviewer_posture} work_item_count={d.work_item_count} attention_required_count={d.attention_required_count} digest={d.review_digest_digest}"
        )
    return 0 if result.status in SUCCESS_STATUSES else 1


if __name__ == "__main__":
    raise SystemExit(main())
