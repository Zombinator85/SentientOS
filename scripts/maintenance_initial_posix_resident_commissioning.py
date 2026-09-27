from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.control_plane_kernel import get_control_plane_kernel
from sentientos.maintenance_initial_posix_resident_commissioning import (
    CommissioningError, approval_bindings, commission, doctor, load_manifest, prepare_intent, verify,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exact initial POSIX resident commissioning")
    parser.add_argument("command", choices=("doctor", "prepare-intent", "show-approval-bindings", "commission", "status", "verify"))
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--approval")
    parser.add_argument("--correlation-id", default="initial-resident-commissioning")
    args = parser.parse_args(argv); manifest = load_manifest(args.manifest)
    try:
        if args.command == "doctor": result = doctor(manifest)
        elif args.command == "prepare-intent": result = prepare_intent(manifest)
        elif args.command == "show-approval-bindings": result = approval_bindings(prepare_intent(manifest))
        elif args.command in {"status", "verify"}: result = verify(manifest)
        else:
            if not args.approval:
                result = {"status": "initial_resident_commissioning_operator_approval_required"}
            else:
                approval = json.loads(Path(args.approval).read_text(encoding="utf-8"))
                result = commission(manifest, approval, kernel=get_control_plane_kernel(), correlation_id=args.correlation_id)
    except CommissioningError as exc:
        result = {"status": "initial_resident_commissioning_blocked", "reason_codes": [exc.code]}
    print(json.dumps(result, sort_keys=True)); return 0 if "blocked" not in str(result.get("status")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
