from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from sentientos.work_item_lifecycle_final_attestation import PASS_STATUSES, WorkItemLifecycleFinalAttestationPolicy, WorkItemLifecycleFinalAttestationRequest, evaluate_work_item_lifecycle_final_attestation, write_work_item_lifecycle_final_attestation_bundle


def _load(path: Path | None) -> dict[str, object] | None:
    if path is None:
        return None
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--completion-dossier", required=True, type=Path)
    p.add_argument("--verification-report", required=True, type=Path)
    p.add_argument("--proposal", type=Path)
    p.add_argument("--closure-run", type=Path)
    p.add_argument("--matrix-report", type=Path)
    p.add_argument("--proof-bundle", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--summary", action="store_true")
    p.add_argument("--require-matrix", action="store_true")
    p.add_argument("--require-proof-bundle", action="store_true")
    p.add_argument("--require-artifacts", action="store_true")
    p.add_argument("--allow-warnings", action=argparse.BooleanOptionalAction, default=False)
    args = p.parse_args(argv)

    result = evaluate_work_item_lifecycle_final_attestation(
        WorkItemLifecycleFinalAttestationRequest(
            completion_dossier=_load(args.completion_dossier) or {},
            verification_report=_load(args.verification_report) or {},
            proposal=_load(args.proposal),
            closure_run=_load(args.closure_run),
            matrix_report=_load(args.matrix_report),
            proof_bundle=_load(args.proof_bundle),
        ),
        policy=WorkItemLifecycleFinalAttestationPolicy(
            allow_warnings=args.allow_warnings,
            matrix_required=args.require_matrix,
            proof_bundle_required=args.require_proof_bundle,
            artifact_refs_required=args.require_artifacts,
        ),
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if args.output:
        write_work_item_lifecycle_final_attestation_bundle(result, args.output)
    if args.summary:
        b = result.bundle
        print(f"status={result.status} work_item_id={b.work_item_id} verification_status={b.verification_status} digest={b.final_attestation_bundle_digest}")
    return 0 if result.status in PASS_STATUSES else 1


if __name__ == "__main__":
    raise SystemExit(main())
