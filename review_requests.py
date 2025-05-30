import os
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
import datetime

REQUESTS_FILE = Path(os.getenv("REVIEW_REQUESTS_FILE", "logs/review_requests.jsonl"))
REQUESTS_FILE.parent.mkdir(parents=True, exist_ok=True)


def log_request(
    kind: str,
    target: str,
    reason: str,
    *,
    agent: Optional[str] = None,
    persona: Optional[str] = None,
    policy: Optional[str] = None,
) -> str:
    """Record a proactive review or policy suggestion."""
    entry_id = uuid.uuid4().hex[:8]
    entry = {
        "id": entry_id,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "kind": kind,
        "target": target,
        "reason": reason,
        "agent": agent,
        "persona": persona,
        "policy": policy,
        "status": "pending",
    }
    with REQUESTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry_id


def list_requests(status: Optional[str] = None) -> List[Dict[str, Any]]:
    if not REQUESTS_FILE.exists():
        return []
    lines = REQUESTS_FILE.read_text(encoding="utf-8").splitlines()
    out: List[Dict[str, Any]] = []
    for ln in lines:
        try:
            entry = json.loads(ln)
        except Exception:
            continue
        if status and entry.get("status") != status:
            continue
        out.append(entry)
    return out


def update_request(request_id: str, status: str) -> bool:
    if not REQUESTS_FILE.exists():
        return False
    lines = REQUESTS_FILE.read_text(encoding="utf-8").splitlines()
    changed = False
    new_lines = []
    for ln in lines:
        try:
            entry = json.loads(ln)
        except Exception:
            new_lines.append(ln)
            continue
        if entry.get("id") == request_id:
            entry["status"] = status
            changed = True
        new_lines.append(json.dumps(entry, ensure_ascii=False))
    if changed:
        REQUESTS_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return changed
