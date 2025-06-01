import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List


def _append(path: Path, entry: Dict[str, str]) -> Dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def log_support(
    name: str, message: str, amount: str = ""
) -> Dict[str, str]:
    """Record a supporter blessing in the living ledger."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "supporter": name,
        "message": message,
        "amount": amount,
        "ritual": "Sanctuary blessing acknowledged and remembered.",
    }
    return _append(Path("logs/support_log.jsonl"), entry)

# Backwards compatibility
log_supporter = log_support


def log_federation(peer: str, email: str = "", message: str = "Federation sync") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "peer": peer,
        "email": email,
        "message": message,
        "ritual": "Federation blessing recorded.",
    }
    return _append(Path("logs/federation_log.jsonl"), entry)


def summarize_log(path: Path, limit: int = 3) -> Dict[str, List[Dict[str, str]]]:
    """Return count and last few entries for a ledger file."""
    if not path.exists():
        return {"count": 0, "recent": []}
    lines = path.read_text(encoding="utf-8").splitlines()
    count = len(lines)
    recent: List[Dict[str, str]] = []
    for ln in lines[-limit:]:
        try:
            recent.append(json.loads(ln))
        except Exception:
            continue
    return {"count": count, "recent": recent}

# Backwards compatibility
summary = summarize_log
