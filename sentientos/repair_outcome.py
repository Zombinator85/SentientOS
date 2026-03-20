"""Deterministic repair outcome verification lifecycle."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from sentientos.audit_chain_gate import verify_audit_chain
from sentientos.federated_enforcement_policy import resolve_policy
from sentientos.immutability import read_manifest


@dataclass(frozen=True)
class RepairOutcome:
    status: str
    reason: str
    checks: list[dict[str, object]]
    closure_action: str
    closure_allowed: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason": self.reason,
            "checks": self.checks,
            "closure_action": self.closure_action,
            "closure_allowed": self.closure_allowed,
        }


def verify_repair_outcome(*, anomaly_kind: str, pre_details: Mapping[str, object] | None = None) -> RepairOutcome:
    checks: list[dict[str, object]] = []
    try:
        audit = verify_audit_chain(Path.cwd())
        checks.append({"name": "audit_chain", "ok": bool(audit.ok), "status": audit.status})
    except Exception as exc:
        checks.append({"name": "audit_chain", "ok": False, "status": f"error:{exc}"})

    try:
        read_manifest()
        checks.append({"name": "immutable_manifest", "ok": True, "status": "ok"})
    except Exception as exc:
        checks.append({"name": "immutable_manifest", "ok": False, "status": f"error:{exc}"})

    if isinstance(pre_details, Mapping):
        symptom_cleared = bool(pre_details.get("symptom_cleared", True))
    else:
        symptom_cleared = True
    checks.append({"name": "symptom_cleared", "ok": symptom_cleared, "status": "cleared" if symptom_cleared else "persisting", "anomaly_kind": anomaly_kind})

    ok = all(bool(c.get("ok")) for c in checks)
    policy = resolve_policy()
    mode = policy.repair_verification
    status = "verified" if ok else "unverified"
    closure_action = "observe"
    closure_allowed = True
    if not ok and mode == "enforce":
        reason = "verification_required_for_closure"
        closure_action = "deny"
        closure_allowed = False
    elif not ok and mode == "advisory":
        reason = "verification_warning"
        closure_action = "warn"
    else:
        reason = "ok" if ok else "verification_observed"
    outcome = RepairOutcome(
        status=status,
        reason=reason,
        checks=checks,
        closure_action=closure_action,
        closure_allowed=closure_allowed,
    )

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(f"glow/repairs/repair_outcome_report_{ts}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "enforcement_policy": policy.to_dict(), "repair_verification_mode": mode, **outcome.to_dict()}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (out.parent / "repair_outcomes.jsonl").open("a", encoding="utf-8") as h:
        h.write(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "enforcement_policy": policy.to_dict(), "repair_verification_mode": mode, **outcome.to_dict()}, sort_keys=True) + "\n")
    return outcome
