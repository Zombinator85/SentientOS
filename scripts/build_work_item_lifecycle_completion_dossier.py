from __future__ import annotations

import argparse
import json
from typing import Any, cast
from pathlib import Path

from sentientos.work_item_lifecycle_completion_dossier import WorkItemLifecycleCompletionPolicy, WorkItemLifecycleCompletionRequest, evaluate_work_item_lifecycle_completion_dossier, write_work_item_lifecycle_completion_dossier


def _load(path: Path | None) -> dict[str, object] | None:
    if path is None:
        return None
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--closure-run", type=Path, required=True)
    p.add_argument("--proposal", type=Path, required=True)
    p.add_argument("--closure-review", type=Path)
    p.add_argument("--verification-run", type=Path)
    p.add_argument("--execution-run", type=Path)
    p.add_argument("--execution-review", type=Path)
    p.add_argument("--preflight-run", type=Path)
    p.add_argument("--admission-run", type=Path)
    p.add_argument("--operator-review", type=Path)
    p.add_argument("--promotion-dossier", type=Path)
    p.add_argument("--review-packet", type=Path)
    p.add_argument("--intake-packet", type=Path)
    p.add_argument("--matrix-report", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--summary", action="store_true")
    p.add_argument("--require-matrix", action="store_true")
    p.add_argument("--require-artifacts", action="store_true")
    p.add_argument("--require-full-chain", action="store_true")
    p.add_argument("--allow-warning-closure", action=argparse.BooleanOptionalAction, default=False)
    a = p.parse_args(argv)

    result = evaluate_work_item_lifecycle_completion_dossier(
        WorkItemLifecycleCompletionRequest(
            lifecycle_closure_run_packet=_load(a.closure_run) or {}, proposal=_load(a.proposal), closure_review_packet=_load(a.closure_review), verification_run_packet=_load(a.verification_run),
            execution_run_packet=_load(a.execution_run), execution_review_packet=_load(a.execution_review), preflight_run_packet=_load(a.preflight_run), admission_run_packet=_load(a.admission_run),
            operator_admission_review_packet=_load(a.operator_review), promotion_dossier=_load(a.promotion_dossier), review_packet=_load(a.review_packet), intake_packet=_load(a.intake_packet), matrix_report=_load(a.matrix_report),
        ),
        policy=WorkItemLifecycleCompletionPolicy(allow_warning_closure=a.allow_warning_closure, full_chain_required=a.require_full_chain, matrix_required=a.require_matrix, artifacts_required=a.require_artifacts),
    )
    if a.output:
        write_work_item_lifecycle_completion_dossier(result, a.output)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if a.summary:
        d = result.dossier
        print(f"status={result.status} work_item_id={d.work_item_id} closure_status={d.lifecycle_closure_run_status} digest={d.completion_dossier_digest}")
    return 0 if result.status in {"lifecycle_completion_dossier_complete", "lifecycle_completion_dossier_complete_with_warnings", "lifecycle_completion_dossier_manual_review_required"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
