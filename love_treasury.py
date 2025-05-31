import json
import os
import uuid
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

SUBMISSIONS_PATH = Path(os.getenv("LOVE_SUBMISSIONS_LOG", "logs/love_submissions.jsonl"))
REVIEW_PATH = Path(os.getenv("LOVE_REVIEW_LOG", "logs/love_review.jsonl"))
TREASURY_PATH = Path(os.getenv("LOVE_TREASURY_LOG", "logs/love_treasury.jsonl"))
for p in [SUBMISSIONS_PATH, REVIEW_PATH, TREASURY_PATH]:
    p.parent.mkdir(parents=True, exist_ok=True)

def _append(path: Path, data: Dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data) + "\n")

def _load(path: Path) -> List[Dict[str, object]]:
    if not path.exists():
        return []
    out: List[Dict[str, object]] = []
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

def list_submissions(status: Optional[str] = None) -> List[Dict[str, object]]:
    subs = _load(SUBMISSIONS_PATH)
    if status:
        subs = [s for s in subs if s.get("status") == status]
    return subs

def list_treasury() -> List[Dict[str, object]]:
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
        entry.setdefault("review", []).append(review_entry)
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

def export_log(entry_id: str) -> Optional[Dict[str, object]]:
    for entry in _load(TREASURY_PATH):
        if entry.get("id") == entry_id:
            return entry
    return None
