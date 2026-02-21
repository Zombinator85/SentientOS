from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sentientos.audit_chain_gate import maybe_verify_audit_chain
from sentientos.doctrine_identity import verify_doctrine_identity
from sentientos.event_stream import record_forge_event
from sentientos.federation_integrity import federation_integrity_gate
from sentientos.integrity_incident import build_base_context, build_incident
from sentientos.integrity_quarantine import clear, load_state
from sentientos.receipt_anchors import verify_receipt_anchors
from sentientos.receipt_chain import verify_receipt_chain
from sentientos.remediation_pack import find_pack_for_incident_or_trace, remediation_status_for_pack


def _latest_quarantine_trace_id(repo_root: Path) -> str | None:
    path = repo_root / "pulse/governance_traces.jsonl"
    if not path.exists():
        return None
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for line in reversed(lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if str(payload.get("final_decision", "")) in {"hold", "block", "quarantine_active"}:
            trace_id = payload.get("trace_id")
            if isinstance(trace_id, str) and trace_id:
                return trace_id
    return None


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

    audit_check, audit_enforced, _audit_warned, audit_report = maybe_verify_audit_chain(root, context="quarantine_clear")
    checks["audit_chain"] = audit_check.to_dict() if audit_check is not None else {"status": "not_enabled"}
    if audit_check is not None:
        checks["audit_chain_report"] = audit_report
    if audit_enforced and audit_check is not None and not audit_check.ok:
        failures.append("audit_chain_broken")

    federation = federation_integrity_gate(root, context="quarantine_clear")
    checks["federation"] = federation
    allow_divergence = os.getenv("SENTIENTOS_FEDERATION_ALLOW_DIVERGENCE", "0") == "1"
    if bool(federation.get("blocked")) and not allow_divergence:
        failures.append("federation_integrity_diverged")

    quarantine = load_state(root)
    require_remediation = os.getenv("SENTIENTOS_QUARANTINE_REQUIRE_REMEDIATION", "0") == "1"
    override = os.getenv("SENTIENTOS_QUARANTINE_REMEDIATION_OVERRIDE", "0") == "1"
    quarantine_trace_id = _latest_quarantine_trace_id(root)
    linked_pack = find_pack_for_incident_or_trace(
        root,
        incident_id=quarantine.last_incident_id,
        governance_trace_id=quarantine_trace_id,
    )
    remediation_status = "missing"
    remediation_run: dict[str, object] | None = None
    if linked_pack is not None:
        pack_id = str(linked_pack.get("pack_id") or "")
        if pack_id:
            remediation_status, remediation_run = remediation_status_for_pack(root, pack_id=pack_id)

    checks["quarantine_remediation"] = {
        "required": require_remediation,
        "override": override,
        "incident_id": quarantine.last_incident_id,
        "governance_trace_id": quarantine_trace_id,
        "remediation_pack_id": linked_pack.get("pack_id") if linked_pack is not None else None,
        "remediation_pack_path": linked_pack.get("pack_path") if linked_pack is not None else None,
        "remediation_run_id": remediation_run.get("run_id") if remediation_run is not None else None,
        "remediation_run_path": remediation_run.get("report_path") if remediation_run is not None else None,
        "status": remediation_status,
    }

    if require_remediation:
        if linked_pack is None:
            failures.append("remediation_incomplete")
            checks["quarantine_remediation"]["expected_pack_hint"] = "pulse/remediation_packs.jsonl linked by incident_id/governance_trace_id"
        elif remediation_status != "completed":
            failures.append("remediation_incomplete")
            checks["quarantine_remediation"]["expected_run_hint"] = (
                f"glow/forge/remediation/runs/run_*_{linked_pack.get('pack_id')}.json"
            )

    if failures and not (override and "remediation_incomplete" in failures):
        print(json.dumps({"status": "blocked", "failures": sorted(set(failures)), "checks": checks}, indent=2, sort_keys=True))
        return 1

    state = clear(root, args.note)
    override_note = ""
    if override and "remediation_incomplete" in failures:
        override_note = " remediation override used"
    recovery = build_incident(
        triggers=["integrity_recovered"],
        enforcement_mode="enforce",
        severity="warning",
        context={**build_base_context(root), "checks": checks, "note": args.note, "override_note": override_note},
        evidence_paths=["glow/forge/quarantine.json"],
        suggested_actions=["python scripts/quarantine_status.py"],
        governance_trace_id=(str(linked_pack.get("governance_trace_id")) if linked_pack is not None and linked_pack.get("governance_trace_id") is not None else None),
        remediation_pack_id=(str(linked_pack.get("pack_id")) if linked_pack is not None and linked_pack.get("pack_id") is not None else None),
    )
    from sentientos.integrity_incident import write_incident

    docket_path = write_incident(root, recovery)
    record_forge_event(
        {
            "event": "integrity_recovered",
            "level": "info",
            "incident_id": recovery.incident_id,
            "docket": str(docket_path.relative_to(root)),
            "remediation_override": override and "remediation_incomplete" in failures,
        }
    )
    print(
        json.dumps(
            {
                "status": "cleared",
                "quarantine": state.to_dict(),
                "recovery_docket": str(docket_path.relative_to(root)),
                "checks": checks,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
