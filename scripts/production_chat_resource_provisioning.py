"""Operator CLI for explicit prepare/confirm/create production provisioning."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Sequence

from sentientos.installation_state import (
    InstallationIdentity, InstallationStateError, InstallationStateRegistry,
)
from sentientos.production_chat_resource_provisioning_actuator import (
    ProductionChatResourceProvisioningActuatorError,
    ProductionChatResourceProvisioningRequest, execute_provisioning_intent,
    load_provisioning_request, prepare_provisioning_intent,
)
from sentientos.production_chat_resource_provisioning_bundle_producer import (
    ProductionChatResourceProvisioningBundleProducerError,
)
from sentientos.production_chat_resource_provisioning_request_consumer import (
    ProductionChatResourceProvisioningRequestConsumerError,
    load_published_production_chat_resource_provisioning_request,
)


class _InputModeError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--request")
    prepare.add_argument("--installation-identity")
    prepare.add_argument("--resource-provisioning-id")
    create = commands.add_parser("create")
    create.add_argument("--request")
    create.add_argument("--installation-identity")
    create.add_argument("--resource-provisioning-id")
    create.add_argument("--confirm-intent-digest")
    return parser


def _emit(value: object) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True))


def _resolve_request(
    args: argparse.Namespace,
) -> tuple[ProductionChatResourceProvisioningRequest | bytes | str | Path,
           InstallationStateRegistry | None]:
    file_mode = args.request is not None
    custody_values = (args.installation_identity, args.resource_provisioning_id)
    custody_mode = all(value is not None for value in custody_values)
    if file_mode == custody_mode or any(value is not None for value in custody_values) != custody_mode:
        raise _InputModeError("invalid_request_source_mode")
    if file_mode:
        return load_provisioning_request(args.request), None
    try:
        identity = InstallationIdentity.parse(args.installation_identity)
    except (TypeError, ValueError) as exc:
        raise _InputModeError("invalid_installation_identity") from exc
    registry = InstallationStateRegistry.system()
    handle = registry.open(identity, create=False)
    request_bytes = load_published_production_chat_resource_provisioning_request(
        handle, args.resource_provisioning_id)
    return load_provisioning_request(request_bytes), registry


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        request, registry = _resolve_request(args)
        intent = prepare_provisioning_intent(request)
        if args.command == "prepare":
            _emit({"status": "production_resource_provisioning_intent_ready", "intent": intent.to_dict()})
            return 0
        if (not isinstance(args.confirm_intent_digest, str)
                or _DIGEST.fullmatch(args.confirm_intent_digest) is None):
            raise _InputModeError("invalid_confirmation_digest")
        if args.confirm_intent_digest != intent.intent_digest:
            raise _InputModeError("intent_confirmation_mismatch")
        result = execute_provisioning_intent(
            request, confirmed_intent_digest=args.confirm_intent_digest, registry=registry)
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
            ProductionChatResourceProvisioningBundleProducerError,
            ProductionChatResourceProvisioningRequestConsumerError,
            InstallationStateError, _InputModeError) as exc:
        _emit({"status": "production_resource_provisioning_blocked", "reason_code": exc.code})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
