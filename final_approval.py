from logging_config import get_log_path
import os
import json
import datetime
import re
from pathlib import Path
from typing import List, Optional

APPROVAL_LOG = get_log_path("final_approval.jsonl", "FINAL_APPROVAL_LOG")
APPROVAL_LOG.parent.mkdir(parents=True, exist_ok=True)

APPROVER_FILE = Path(os.getenv("FINAL_APPROVER_FILE", "config/final_approvers.json"))
APPROVER_FILE.parent.mkdir(parents=True, exist_ok=True)

_LAST_APPROVER = ""
_OVERRIDE: Optional[List[str]] = None
_SOURCE = "env"


def _env_decision(name: str) -> bool:
    var = "FOUR_O_APPROVE" if name.lower() in {"4o", "four_o"} else f"{name.upper()}_APPROVE"
    decision = os.getenv(var, "true")
    return decision.lower() in {"1", "true", "yes", "y"}


def load_file_approvers(fp: Path) -> List[str]:
    """Return approvers from a JSON list or newline separated file."""
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        if isinstance(data, list):
            items = [str(a).strip() for a in data if str(a).strip()]
            if items:
                return items
    except Exception:
        pass
    try:
        return [l.strip() for l in fp.read_text(encoding="utf-8").splitlines() if l.strip()]
    except Exception:
        return []


def load_approvers() -> List[str]:
    global _SOURCE
    if _OVERRIDE is not None:
        return list(_OVERRIDE)
    env_val = os.getenv("REQUIRED_FINAL_APPROVER", "4o")
    parts = re.split(r"[,\s]+", env_val)
    approvers = [a.strip() for a in parts if a.strip()]
    _SOURCE = "env"
    if APPROVER_FILE.exists():
        try:
            data = load_file_approvers(APPROVER_FILE)
            if data:
                approvers = data
                _SOURCE = "file"
        except Exception:
            pass
    return approvers or ["4o"]


def set_approvers(approvers: List[str]) -> None:
    """Persist approver chain and set as override."""
    global _OVERRIDE, _SOURCE
    APPROVER_FILE.write_text(json.dumps(approvers, ensure_ascii=False, indent=2), encoding="utf-8")
    _OVERRIDE = list(approvers)
    _SOURCE = "file"


def override_approvers(approvers: List[str], *, source: str = "cli") -> None:
    """Temporarily override approver chain without writing to disk."""
    global _OVERRIDE, _SOURCE
    _OVERRIDE = list(approvers)
    _SOURCE = source


def last_approver() -> str:
    return _LAST_APPROVER


def approver_source() -> str:
    """Return how the current approver list was determined."""
    return _SOURCE


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
            "source": _SOURCE,
        }
        if rationale:
            entry["rationale"] = rationale
        with APPROVAL_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        if not ok:
            approved = False
            break
    return approved
