"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import json
import os
import uuid
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Mapping, Any

FEDERATED_PATH = get_log_path("federated_love.jsonl", "LOVE_FEDERATED_LOG")
FEDERATED_PATH.parent.mkdir(parents=True, exist_ok=True)

SUBMISSIONS_PATH = get_log_path("love_submissions.jsonl", "LOVE_SUBMISSIONS_LOG")
REVIEW_PATH = get_log_path("love_review.jsonl", "LOVE_REVIEW_LOG")
TREASURY_PATH = get_log_path("love_treasury.jsonl", "LOVE_TREASURY_LOG")
for p in [SUBMISSIONS_PATH, REVIEW_PATH, TREASURY_PATH]:
    p.parent.mkdir(parents=True, exist_ok=True)

def _append(path: Path, data: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data) + "\n")

def _load(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out

def submit_log(title: str, participants: List[str], time_span: str, summary: str,
               log_text: str, *, user: str = "anon", note: str = "") -> str:
    sid = uuid.uuid4().hex[:8]
    digest = hashlib.sha256(log_text.encode("utf-8")).hexdigest()
    entry = {
        "id": sid,
        "time": datetime.utcnow().isoformat(),
        "title": title,
        "participants": participants,
        "time_span": time_span,
        "summary": summary,
        "hash": digest,
        "note": note,
        "user": user,
        "log": log_text,
        "status": "pending",
        "review": []
    }
    _append(SUBMISSIONS_PATH, entry)
    return sid

def list_submissions(status: Optional[str] = None) -> List[Dict[str, Any]]:
    subs = _load(SUBMISSIONS_PATH)
    if status:
        subs = [s for s in subs if s.get("status") == status]
    return subs

def list_treasury() -> List[Dict[str, Any]]:
    return _load(TREASURY_PATH)

def review_log(submission_id: str, reviewer: str, action: str,
               *, note: str = "", cosign: Optional[str] = None) -> bool:
    subs = _load(SUBMISSIONS_PATH)
    updated = False
    for entry in subs:
        if entry.get("id") != submission_id:
            continue
        review_entry = {
            "time": datetime.utcnow().isoformat(),
            "user": reviewer,
            "action": action,
            "note": note,
        }
        if cosign:
            review_entry["cosign"] = cosign
        reviews = entry.setdefault("review", [])
        if isinstance(reviews, list):
            reviews.append(review_entry)
        _append(REVIEW_PATH, {"id": submission_id, **review_entry})
        if action == "affirm":
            entry["status"] = "enshrined"
            _append(TREASURY_PATH, entry)
            subs = [s for s in subs if s.get("id") != submission_id]
        else:
            entry["status"] = action
        updated = True
        break
    if updated:
        with SUBMISSIONS_PATH.open("w", encoding="utf-8") as f:
            for s in subs:
                f.write(json.dumps(s) + "\n")
    return updated

def export_log(entry_id: str) -> Optional[Dict[str, Any]]:
    for entry in _load(TREASURY_PATH):
        if entry.get("id") == entry_id:
            return entry
    return None


def list_federated() -> List[Dict[str, Any]]:
    """Return logs imported from other cathedrals."""
    return _load(FEDERATED_PATH)


def import_federated(entry: Dict[str, Any], origin: str) -> bool:
    """Import a log from another cathedral if not already present."""
    existing = _load(FEDERATED_PATH)
    for e in existing:
        if e.get("id") == entry.get("id") and e.get("origin") == origin:
            return False
    entry = dict(entry)
    entry["origin"] = origin
    entry["import_time"] = datetime.utcnow().isoformat()
    _append(FEDERATED_PATH, entry)
    return True


def federation_metadata() -> List[Dict[str, Any]]:
    """Return lightweight metadata about enshrined logs."""
    out = []
    for entry in _load(TREASURY_PATH):
        out.append({
            "id": entry.get("id"),
            "hash": entry.get("hash"),
            "time": entry.get("time"),
            "title": entry.get("title"),
        })
    return out


def list_global() -> List[Dict[str, Any]]:
    """Combine local and federated logs for browsing."""
    return _load(TREASURY_PATH) + _load(FEDERATED_PATH)
