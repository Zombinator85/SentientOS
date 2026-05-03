from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
from logging_config import get_log_path
from sentientos.control_api import AuthorizationError
from sentientos.control_api import require_self_patch_apply_authority

"""Autonomous Self-Patching Agent
Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List


GOVERNANCE_ANNOTATION = "phase39_boundary_non_sovereign_autonomy"
ADMISSION_SURFACE = "caller-invoked CLI/function call with control_api authority checks"
CONSENT_BOUNDARY = "explicit caller invocation; no autonomous background scheduling"
PROVENANCE_BOUNDARY = "append-only self_patch_agent log entries with UTC timestamps"
SIMULATION_ONLY = False
NON_SOVEREIGNTY = "agent name is historical; execution remains bounded, caller-triggered, and policy-gated"

LOG_PATH = get_log_path("self_patch_agent.jsonl", "SELF_PATCH_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def propose(description: str) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "description": description, "status": "proposed"}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def _require_apply_authority(
    admission_token: object | None,
    authorization: object | None,
) -> None:
    require_self_patch_apply_authority(admission_token, authorization)


def apply(
    patch_id: int,
    *,
    admission_token: object | None = None,
    authorization: object | None = None,
) -> Dict[str, str]:
    _require_apply_authority(admission_token, authorization)
    entry = {"timestamp": datetime.utcnow().isoformat(), "patch_id": patch_id, "status": "applied"}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(limit: int = 20) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Autonomous Self-Patching Agent")
    sub = ap.add_subparsers(dest="cmd")

    pr = sub.add_parser("propose", help="Propose a patch")
    pr.add_argument("description")
    pr.set_defaults(func=lambda a: print(json.dumps(propose(a.description), indent=2)))

    aply = sub.add_parser("apply", help="Apply a patch")
    aply.add_argument("patch_id", type=int)
    aply.set_defaults(func=lambda a: print(json.dumps(apply(a.patch_id), indent=2)))

    hs = sub.add_parser("history", help="Show patch history")
    hs.add_argument("--limit", type=int, default=20)
    hs.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        try:
            args.func(args)
        except AuthorizationError as exc:  # pragma: no cover - CLI safeguard
            print(json.dumps({"status": "rejected", "reason": str(exc)}))
            raise SystemExit(1)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
