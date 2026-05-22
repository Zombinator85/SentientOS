from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

from sentientos.work_item_lifecycle_attestation_index_verifier import PASS_STATUSES, WorkItemLifecycleAttestationIndexVerificationPolicy, WorkItemLifecycleAttestationIndexVerificationRequest, evaluate_work_item_lifecycle_attestation_index_verification, write_work_item_lifecycle_attestation_index_verification_report


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--attestation-index", required=True, type=Path)
    p.add_argument("--attestation-bundle", action="append", dest="attestation_bundles", type=Path, default=[])
    p.add_argument("--matrix-report", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--summary", action="store_true")
    p.add_argument("--require-matrix", action="store_true")
    p.add_argument("--require-source-bundles", action="store_true")
    p.add_argument("--allow-warning-index", action=argparse.BooleanOptionalAction, default=False)
    args = p.parse_args(argv)

    result = evaluate_work_item_lifecycle_attestation_index_verification(
        WorkItemLifecycleAttestationIndexVerificationRequest(
            attestation_index=_load(args.attestation_index),
            attestation_bundles=tuple((str(path), _load(path)) for path in args.attestation_bundles),
            matrix_report=_load(args.matrix_report) if args.matrix_report else None,
        ),
        policy=WorkItemLifecycleAttestationIndexVerificationPolicy(
            allow_warning_index=args.allow_warning_index,
            source_bundles_required=args.require_source_bundles,
            matrix_required=args.require_matrix,
        ),
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if args.output:
        write_work_item_lifecycle_attestation_index_verification_report(result, args.output)
    if args.summary:
        r = result.report
        print(f"status={result.status} index_id={r.attestation_index_id} finding_count={r.finding_count} digest={r.index_verification_report_digest}")
    return 0 if result.status in PASS_STATUSES else 1


if __name__ == "__main__":
    raise SystemExit(main())
