import os
import json
import uuid
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

REQUESTS_FILE = Path(os.getenv("REVIEW_REQUESTS_FILE", "logs/review_requests.jsonl"))
AUDIT_FILE = Path(os.getenv("SUGGESTION_AUDIT_FILE", "logs/suggestion_audit.jsonl"))
REQUESTS_FILE.parent.mkdir(parents=True, exist_ok=True)
AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)


def _audit(action: str, request_id: str, **meta: Any) -> None:
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "action": action,
        "request": request_id,
        **meta,
    }
    with AUDIT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


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


def log_policy_suggestion(
    kind: str,
    target: str,
    suggestion: str,
    rationale: str,
    *,
    agent: Optional[str] = None,
    persona: Optional[str] = None,
    policy: Optional[str] = None,
    assign: Optional[str] = None,
) -> str:
    """Create a policy/reflex suggestion with rationale."""
    entry_id = uuid.uuid4().hex[:8]
    entry = {
        "id": entry_id,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "kind": kind,
        "target": target,
        "suggestion": suggestion,
        "rationale": rationale,
        "agent": agent,
        "persona": persona,
        "policy": policy,
        "assigned": assign,
        "status": "pending",
        "votes": {},
        "comments": [],
    }
    with REQUESTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    _audit("create", entry_id, by=agent or "system")
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


def get_request(request_id: str) -> Optional[Dict[str, Any]]:
    for entry in list_requests():
        if entry.get("id") == request_id:
            return entry
    return None


def _rewrite(entries: List[Dict[str, Any]]) -> None:
    REQUESTS_FILE.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n", encoding="utf-8")


def comment_request(request_id: str, user: str, text: str) -> bool:
    entries = list_requests()
    changed = False
    for e in entries:
        if e.get("id") == request_id:
            e.setdefault("comments", []).append({
                "user": user,
                "text": text,
                "timestamp": datetime.datetime.utcnow().isoformat(),
            })
            changed = True
            _audit("comment", request_id, by=user)
    if changed:
        _rewrite(entries)
    return changed


def vote_request(request_id: str, user: str, upvote: bool = True, threshold: int = 2) -> bool:
    entries = list_requests()
    changed = False
    for e in entries:
        if e.get("id") == request_id:
            votes = e.setdefault("votes", {})
            votes[user] = 1 if upvote else -1
            pos = sum(1 for v in votes.values() if v > 0)
            if pos >= threshold and e.get("status") == "pending":
                e["status"] = "approved"
                _audit("auto_approve", request_id)
            changed = True
            _audit("vote", request_id, by=user, value=1 if upvote else -1)
    if changed:
        _rewrite(entries)
    return changed


def assign_request(request_id: str, *, agent: Optional[str] = None, persona: Optional[str] = None) -> bool:
    entries = list_requests()
    changed = False
    for e in entries:
        if e.get("id") == request_id:
            ass = e.setdefault("assigned", [])
            if agent:
                ass.append(f"agent:{agent}")
            if persona:
                ass.append(f"persona:{persona}")
            changed = True
            _audit("assign", request_id, agent=agent, persona=persona)
    if changed:
        _rewrite(entries)
    return changed


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


def implement_request(request_id: str) -> bool:
    if update_request(request_id, "implemented"):
        _audit("implement", request_id)
        return True
    return False


def dismiss_request(request_id: str) -> bool:
    if update_request(request_id, "dismissed"):
        _audit("dismiss", request_id)
        return True
    return False
