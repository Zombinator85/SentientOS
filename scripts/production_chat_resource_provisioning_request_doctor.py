#!/usr/bin/env python
"""Inspect fixed provisioning-request publication custody without changing it."""
from __future__ import annotations

import argparse
import json
from typing import Sequence

from sentientos.installation_state import (
    InstallationIdentity, InstallationStateError, InstallationStateRegistry,
)
from sentientos.production_chat_resource_provisioning_request_doctor import (
    ProductionChatResourceProvisioningRequestDoctorError,
    diagnose_production_chat_resource_provisioning_request_publication,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation-identity", required=True)
    parser.add_argument("--resource-provisioning-id", required=True)
    parser.add_argument("--summary", action="store_true")
    return parser


def _emit(value: object) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True))


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        try:
            identity = InstallationIdentity.parse(args.installation_identity)
        except (TypeError, ValueError) as exc:
            raise ProductionChatResourceProvisioningRequestDoctorError(
                "invalid_installation_identity") from exc
        registry = InstallationStateRegistry.system()
        handle = registry.open(identity, create=False)
        report = diagnose_production_chat_resource_provisioning_request_publication(
            handle, args.resource_provisioning_id).to_dict()
        if args.summary:
            report = {key: report[key] for key in (
                "doctor_report_id", "overall_doctor_status", "custody_shape",
                "publication_complete", "next_inspection_guidance")}
        _emit(report)
        return 0
    except (ProductionChatResourceProvisioningRequestDoctorError,
            InstallationStateError, OSError) as exc:
        code = getattr(exc, "code", "installation_state_unavailable")
        _emit({"status": "publication_doctor_blocked", "reason_code": code})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
