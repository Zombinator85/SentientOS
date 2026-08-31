"""Inspect or explicitly execute bounded production model artifact acquisition."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any
from sentientos.local_model_artifact_acquisition import (ModelArtifactAcquisitionError, acquire_model_artifact,
    authorization_for, compose_acquisition_plan, default_escrow_root)

def _read(path: Path) -> dict[str, Any]:
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("input_must_be_object")
    return value

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection-plan", type=Path, required=True)
    parser.add_argument("--runtime-provisioning-plan", type=Path, required=True)
    parser.add_argument("--backend-verification-receipt", type=Path, required=True)
    parser.add_argument("--local-model-catalog", type=Path, required=True)
    parser.add_argument("--escrow-root", type=Path, default=default_escrow_root())
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-plan-digest")
    args = parser.parse_args(argv)
    try:
        plan = compose_acquisition_plan(_read(args.selection_plan), _read(args.runtime_provisioning_plan),
            _read(args.backend_verification_receipt), _read(args.local_model_catalog), args.escrow_root)
        if args.execute and args.confirm_plan_digest != plan["acquisition_plan_digest"]:
            raise ModelArtifactAcquisitionError("confirmed_plan_digest_mismatch")
        result = acquire_model_artifact(plan, execute=args.execute,
            authorization=authorization_for(plan, operator_confirmed=True) if args.execute else None)
    except (OSError, ValueError, json.JSONDecodeError, ModelArtifactAcquisitionError) as exc:
        code = exc.code if isinstance(exc, ModelArtifactAcquisitionError) else "invalid_input_evidence"
        print(json.dumps({"status": "blocked", "reason_code": code}, sort_keys=True)); return 2
    print(json.dumps({"plan": plan, "result": result}, sort_keys=True, indent=2)); return 0

if __name__ == "__main__": raise SystemExit(main())
