"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import os
import json
import uuid
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import final_approval

REQUESTS_FILE = get_log_path("review_requests.jsonl", "REVIEW_REQUESTS_FILE")
AUDIT_FILE = get_log_path("suggestion_audit.jsonl", "SUGGESTION_AUDIT_FILE")
REQUESTS_FILE.parent.mkdir(parents=True, exist_ok=True)
AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)


def _audit(action: str, request_id: str, **meta: Any) -> None:
    entry: Dict[str, Any] = {
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
    entry: Dict[str, Any] = {
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
    previous: Optional[str] = None,
) -> str:
    """Create a policy/reflex suggestion with rationale."""
    entry_id = uuid.uuid4().hex[:8]
    entry: Dict[str, Any] = {
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
        "previous": previous,
        "rationale_log": [],
        "refined": False,
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


def _refine_rationale(entry: Dict[str, Any]) -> bool:
    """Update rationale summary based on votes/comments."""
    up = sum(1 for v in entry.get("votes", {}).values() if v > 0)
    down = sum(1 for v in entry.get("votes", {}).values() if v < 0)
    com = len(entry.get("comments", []))
    summary = f"{up} upvotes, {down} downvotes, {com} comments"
    log = entry.setdefault("rationale_log", [])
    if log and log[-1].get("summary") == summary:
        return False
    log.append({"summary": summary, "timestamp": datetime.datetime.utcnow().isoformat()})
    entry["rationale"] = entry.get("rationale", "") + f"\nRefined: {summary}"
    entry["refined"] = True
    return True


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
            if _refine_rationale(e):
                _audit("rationale_refine", request_id)
            if e.get("status") in {"implemented", "dismissed"} and any(k in text.lower() for k in ["fail", "issue", "again"]):
                new_id = chain_suggestion(
                    request_id,
                    f"Follow-up to {request_id}",
                    text,
                    agent=e.get("agent"),
                    persona=e.get("persona"),
                    policy=e.get("policy"),
                )
                new_entry = get_request(new_id)
                if new_entry:
                    entries.append(new_entry)
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
            if _refine_rationale(e):
                _audit("rationale_refine", request_id)
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


def implement_request(request_id: str, approvers: Optional[list[str]] = None) -> bool:
    entry = get_request(request_id)
    desc = str(entry.get("suggestion") if entry else request_id)
    if approvers is not None:
        approved = final_approval.request_approval(desc, approvers=approvers)
    else:
        approved = final_approval.request_approval(desc)
    if not approved:
        _audit("blocked", request_id, approver=final_approval.last_approver())
        return False
    if update_request(request_id, "implemented"):
        _audit("implement", request_id)
        return True
    return False


def dismiss_request(request_id: str) -> bool:
    if update_request(request_id, "dismissed"):
        _audit("dismiss", request_id)
        return True
    return False


def chain_suggestion(
    previous_id: str,
    suggestion: str,
    rationale: str,
    *,
    agent: Optional[str] = None,
    persona: Optional[str] = None,
    policy: Optional[str] = None,
) -> str:
    prev = get_request(previous_id)
    target = str(prev.get("target") if prev else "")
    kind_val = str(prev.get("kind", "workflow")) if prev else "workflow"
    sid = log_policy_suggestion(
        kind_val,
        target,
        suggestion,
        rationale,
        agent=agent,
        persona=persona,
        policy=policy,
        previous=previous_id,
    )
    _audit("chain", sid, previous=previous_id)
    return sid


def get_chain(start_id: str) -> List[Dict[str, Any]]:
    chain: List[Dict[str, Any]] = []
    lookup = {e["id"]: e for e in list_requests()}
    cur = lookup.get(start_id)
    while cur:
        chain.append(cur)
        nxt = next((v for v in lookup.values() if v.get("previous") == cur["id"]), None)
        cur = nxt
    return chain


def get_provenance(request_id: str) -> List[Dict[str, Any]]:
    if not AUDIT_FILE.exists():
        return []
    lines = AUDIT_FILE.read_text(encoding="utf-8").splitlines()
    return [json.loads(l) for l in lines if json.loads(l).get("request") == request_id]
