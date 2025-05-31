import os
import json
import datetime
from pathlib import Path
from typing import List, Optional

APPROVAL_LOG = Path(os.getenv("FINAL_APPROVAL_LOG", "logs/final_approval.jsonl"))
APPROVAL_LOG.parent.mkdir(parents=True, exist_ok=True)

APPROVER_FILE = Path(os.getenv("FINAL_APPROVER_FILE", "config/final_approvers.json"))
APPROVER_FILE.parent.mkdir(parents=True, exist_ok=True)

_LAST_APPROVER = ""


def _env_decision(name: str) -> bool:
    var = "FOUR_O_APPROVE" if name.lower() in {"4o", "four_o"} else f"{name.upper()}_APPROVE"
    decision = os.getenv(var, "true")
    return decision.lower() in {"1", "true", "yes", "y"}


def load_approvers() -> List[str]:
    env_val = os.getenv("REQUIRED_FINAL_APPROVER", "4o")
    approvers = [a.strip() for a in env_val.split(",") if a.strip()]
    if APPROVER_FILE.exists():
        try:
            data = json.loads(APPROVER_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                approvers = [str(a) for a in data if str(a).strip()]
        except Exception:
            pass
    return approvers or ["4o"]


def set_approvers(approvers: List[str]) -> None:
    APPROVER_FILE.write_text(json.dumps(approvers, ensure_ascii=False, indent=2), encoding="utf-8")


def last_approver() -> str:
    return _LAST_APPROVER


def request_approval(description: str, *, approvers: Optional[List[str]] = None, rationale: Optional[str] = None) -> bool:
    """Request approval from all configured approvers."""
    global _LAST_APPROVER
    chain = approvers or load_approvers()
    approved = True
    for name in chain:
        ok = _env_decision(name)
        _LAST_APPROVER = name
        entry = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "approver": name,
            "description": description,
            "approved": ok,
        }
        if rationale:
            entry["rationale"] = rationale
        with APPROVAL_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        if not ok:
            approved = False
            break
    return approved
