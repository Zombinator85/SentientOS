"""Operator CLI for explicit prepare/confirm/create production provisioning."""
from __future__ import annotations

import argparse
import json
from typing import Sequence

from sentientos.installation_state import InstallationStateError
from sentientos.production_chat_resource_provisioning_actuator import (
    ProductionChatResourceProvisioningActuatorError, execute_provisioning_intent,
    load_provisioning_request, prepare_provisioning_intent,
)
from sentientos.production_chat_resource_provisioning_bundle_producer import (
    ProductionChatResourceProvisioningBundleProducerError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--request", required=True)
    create = commands.add_parser("create")
    create.add_argument("--request", required=True)
    create.add_argument("--confirm-intent-digest")
    return parser


def _emit(value: object) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True))


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        request = load_provisioning_request(args.request)
        intent = prepare_provisioning_intent(request)
        if args.command == "prepare":
            _emit({"status": "production_resource_provisioning_intent_ready", "intent": intent.to_dict()})
            return 0
        result = execute_provisioning_intent(
            request, confirmed_intent_digest=args.confirm_intent_digest)
        _emit({
            "status": "production_resource_provisioning_created",
            "installation_identity": result.installation_identity,
            "resource_provisioning_id": result.provisioning_id,
            "intent_digest": intent.intent_digest,
            "manifest_digest": result.manifest_digest,
            "allocation_id": result.allocation_id, "allocation_digest": result.allocation_digest,
            "resource_policy_digest": result.resource_policy_digest,
            "principal_id": result.principal_id,
        })
        return 0
    except (ProductionChatResourceProvisioningActuatorError,
            ProductionChatResourceProvisioningBundleProducerError, InstallationStateError) as exc:
        _emit({"status": "production_resource_provisioning_blocked", "reason_code": exc.code})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
