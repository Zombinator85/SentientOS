from logging_config import get_log_path
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Set

import forgiveness_ledger as fledge

COUNCIL_QUORUM = int(os.getenv("COUNCIL_QUORUM", "2"))

REVIEW_LOG = get_log_path("confessional_review.jsonl", "CONFESSIONAL_REVIEW_LOG")
REVIEW_LOG.parent.mkdir(parents=True, exist_ok=True)


def log_review(confession_ts: str, user: str, note: str, status: str = "resolved") -> Dict[str, Any]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "confession_ts": confession_ts,
        "user": user,
        "note": note,
        "status": status,
    }
    with REVIEW_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def reviewed_timestamps() -> Set[str]:
    if not REVIEW_LOG.exists():
        return set()
    out = set()
    for ln in REVIEW_LOG.read_text(encoding="utf-8").splitlines():
        try:
            out.add(json.loads(ln).get("confession_ts", ""))
        except Exception:
            continue
    return out


def council_status(confession_ts: str) -> str:
    """Return 'resolved' if quorum approvals met."""
    votes = fledge.council_votes(confession_ts)
    approvals = [v for v in votes if v.get("decision") == "approve"]
    return "resolved" if len(approvals) >= COUNCIL_QUORUM else "pending"


def log_council_vote(confession_ts: str, user: str, decision: str, note: str = "") -> Dict[str, Any]:
    """Log a council vote and return ledger entry."""
    entry = fledge.log_council_vote(confession_ts, user, decision, note)
    entry["status"] = council_status(confession_ts)
    return entry
