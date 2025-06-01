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


def streamlit_widget(st_module) -> None:
    """Display ledger summary in a Streamlit dashboard."""
    sup = summarize_log(Path("logs/support_log.jsonl"))
    fed = summarize_log(Path("logs/federation_log.jsonl"))
    st_module.write(
        f"Support blessings: {sup['count']} • Federation blessings: {fed['count']}"
    )
    last_sup = sup["recent"][-1] if sup["recent"] else None
    last_fed = fed["recent"][-1] if fed["recent"] else None
    if last_sup or last_fed:
        st_module.write("Recent entries:")
        st_module.json({"support": last_sup, "federation": last_fed})


def print_summary() -> None:
    """Print a ledger summary to stdout."""
    sup = summarize_log(Path("logs/support_log.jsonl"))
    fed = summarize_log(Path("logs/federation_log.jsonl"))
    data = {
        "support_count": sup["count"],
        "federation_count": fed["count"],
        "support_recent": sup["recent"],
        "federation_recent": fed["recent"],
    }
    print(json.dumps(data, indent=2))
