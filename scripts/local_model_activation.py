from __future__ import annotations

"""JSON CLI for selection-only hardened production activation."""

import argparse
import json
from pathlib import Path

from sentientos.control_plane_kernel import get_control_plane_kernel
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.local_model_production_activation import (
    ProductionActivationError, activate_production, prepare_activation_intent,
    verify_current_activation,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("intent", "activate", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--installation-identity", required=True)
        if name != "verify":
            command.add_argument("--commissioning-receipt-id", required=True)
            command.add_argument("--correlation-id", required=True)
            command.add_argument("--expected-prior-state", required=True)
        if name == "activate":
            command.add_argument("--approval-json", type=Path, required=True)
    args = parser.parse_args()
    try:
        handle = InstallationStateRegistry.system().open(InstallationIdentity.parse(args.installation_identity))
        if args.command == "intent":
            result = dict(prepare_activation_intent(handle,
                commissioning_receipt_id=args.commissioning_receipt_id, correlation_id=args.correlation_id,
                expected_prior_state=args.expected_prior_state))
        elif args.command == "activate":
            approval = json.loads(args.approval_json.read_text(encoding="utf-8"))
            result = activate_production(installation_handle=handle,
                commissioning_receipt_id=args.commissioning_receipt_id, approval_evidence=approval,
                control_plane_kernel=get_control_plane_kernel(), correlation_id=args.correlation_id,
                expected_prior_state=args.expected_prior_state)
        else:
            result = verify_current_activation(handle)
    except (ProductionActivationError, OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"status": "activation_verification_failed", "error": str(exc),
                  "model_loaded": False, "serving_started": False, "inference_performed": False}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result.get("status") not in {"activation_verification_failed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
