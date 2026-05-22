from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

from sentientos.work_item_lifecycle_attestation_index import PASS_STATUSES, WorkItemLifecycleAttestationIndexPolicy, WorkItemLifecycleAttestationIndexRequest, evaluate_work_item_lifecycle_attestation_index, write_work_item_lifecycle_attestation_index


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--attestation-bundle", action="append", dest="attestation_bundles", type=Path, default=[])
    p.add_argument("--matrix-report", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--summary", action="store_true")
    p.add_argument("--allow-skipped-inputs", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--allow-duplicate-work-items", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--require-sealed", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--require-matrix", action="store_true")
    args = p.parse_args(argv)

    bundles = tuple((str(path), _load(path)) for path in args.attestation_bundles)
    result = evaluate_work_item_lifecycle_attestation_index(
        WorkItemLifecycleAttestationIndexRequest(attestation_bundles=bundles, matrix_report=_load(args.matrix_report) if args.matrix_report else None),
        policy=WorkItemLifecycleAttestationIndexPolicy(
            allow_skipped_inputs=args.allow_skipped_inputs,
            allow_duplicate_work_items=args.allow_duplicate_work_items,
            require_sealed=args.require_sealed,
            matrix_required=args.require_matrix,
        ),
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if args.output:
        write_work_item_lifecycle_attestation_index(result, args.output)
    if args.summary:
        i = result.index
        print(f"status={result.status} indexed={i.indexed_count} skipped={i.skipped_count} duplicate={i.duplicate_count} digest={i.attestation_index_digest}")
    return 0 if result.status in PASS_STATUSES else 1


if __name__ == "__main__":
    raise SystemExit(main())
