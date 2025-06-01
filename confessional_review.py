import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Set

REVIEW_LOG = Path(os.getenv("CONFESSIONAL_REVIEW_LOG", "logs/confessional_review.jsonl"))
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
