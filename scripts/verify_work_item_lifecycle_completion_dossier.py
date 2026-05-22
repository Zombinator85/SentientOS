from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from sentientos.work_item_lifecycle_completion_verifier import PASS_STATUSES, WorkItemLifecycleCompletionVerificationPolicy, WorkItemLifecycleCompletionVerificationRequest, evaluate_work_item_lifecycle_completion_verification, write_work_item_lifecycle_completion_verification_report


def _load(path: Path | None) -> dict[str, object] | None:
    if path is None:
        return None
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--completion-dossier", required=True, type=Path)
    p.add_argument("--proposal", type=Path)
    p.add_argument("--closure-run", type=Path)
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
    p.add_argument("--allow-warning-completion", action=argparse.BooleanOptionalAction, default=False)
    a = p.parse_args(argv)

    result = evaluate_work_item_lifecycle_completion_verification(WorkItemLifecycleCompletionVerificationRequest(completion_dossier=_load(a.completion_dossier) or {}, proposal=_load(a.proposal), closure_run_packet=_load(a.closure_run), closure_review_packet=_load(a.closure_review), verification_run_packet=_load(a.verification_run), execution_run_packet=_load(a.execution_run), execution_review_packet=_load(a.execution_review), preflight_run_packet=_load(a.preflight_run), admission_run_packet=_load(a.admission_run), operator_admission_review_packet=_load(a.operator_review), promotion_dossier=_load(a.promotion_dossier), review_packet=_load(a.review_packet), intake_packet=_load(a.intake_packet), matrix_report=_load(a.matrix_report)), policy=WorkItemLifecycleCompletionVerificationPolicy(allow_warning_completion=a.allow_warning_completion, full_chain_required=a.require_full_chain, matrix_required=a.require_matrix, artifact_refs_required=a.require_artifacts))
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if a.output:
        write_work_item_lifecycle_completion_verification_report(result, a.output)
    if a.summary:
        r = result.report
        print(f"status={result.status} work_item_id={r.work_item_id} finding_count={r.finding_count} digest={r.verification_report_digest}")
    return 0 if result.status in PASS_STATUSES else 1


if __name__ == "__main__":
    raise SystemExit(main())
