from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sentientos.doctrine_identity import verify_doctrine_identity
from sentientos.event_stream import record_forge_event
from sentientos.federation_integrity import federation_integrity_gate
from sentientos.integrity_incident import build_base_context, build_incident
from sentientos.integrity_quarantine import clear
from sentientos.receipt_anchors import verify_receipt_anchors
from sentientos.receipt_chain import verify_receipt_chain


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clear integrity quarantine after verification gates pass.")
    parser.add_argument("--note", default="operator recovery", help="Recovery note")
    args = parser.parse_args(argv)

    root = Path.cwd().resolve()
    checks: dict[str, object] = {}
    failures: list[str] = []

    doctrine_ok, doctrine_payload = verify_doctrine_identity(root)
    doctrine_enforce = os.getenv("SENTIENTOS_DOCTRINE_IDENTITY_ENFORCE", "0") == "1"
    checks["doctrine_identity"] = doctrine_payload
    if doctrine_enforce and not doctrine_ok:
        failures.append("doctrine_identity_mismatch")

    chain = verify_receipt_chain(root)
    checks["receipt_chain"] = chain.to_dict()
    if not chain.ok:
        failures.append("receipt_chain_broken")

    anchor_enforce = os.getenv("SENTIENTOS_RECEIPT_ANCHOR_ENFORCE", "0") == "1"
    anchors = verify_receipt_anchors(root)
    checks["receipt_anchors"] = anchors.to_dict()
    if anchor_enforce and not anchors.ok:
        failures.append("receipt_anchor_invalid")

    federation = federation_integrity_gate(root, context="quarantine_clear")
    checks["federation"] = federation
    allow_divergence = os.getenv("SENTIENTOS_FEDERATION_ALLOW_DIVERGENCE", "0") == "1"
    if bool(federation.get("blocked")) and not allow_divergence:
        failures.append("federation_integrity_diverged")

    if failures:
        print(json.dumps({"status": "blocked", "failures": sorted(set(failures)), "checks": checks}, indent=2, sort_keys=True))
        return 1

    state = clear(root, args.note)
    recovery = build_incident(
        triggers=["integrity_recovered"],
        enforcement_mode="enforce",
        severity="warning",
        context={**build_base_context(root), "checks": checks, "note": args.note},
        evidence_paths=["glow/forge/quarantine.json"],
        suggested_actions=["python scripts/quarantine_status.py"],
    )
    from sentientos.integrity_incident import write_incident

    docket_path = write_incident(root, recovery)
    record_forge_event({"event": "integrity_recovered", "level": "info", "incident_id": recovery.incident_id, "docket": str(docket_path.relative_to(root))})
    print(json.dumps({"status": "cleared", "quarantine": state.to_dict(), "recovery_docket": str(docket_path.relative_to(root)), "checks": checks}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
