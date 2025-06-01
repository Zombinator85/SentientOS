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


def _unique_values(path: Path, field: str) -> int:
    if not path.exists():
        return 0
    seen = set()
    for ln in path.read_text(encoding="utf-8").splitlines():
        try:
            val = json.loads(ln).get(field)
        except Exception:
            continue
        if val:
            seen.add(val)
    return len(seen)


def print_summary(limit: int = 3) -> None:
    """Print a ledger summary to stdout."""
    sup_path = Path("logs/support_log.jsonl")
    fed_path = Path("logs/federation_log.jsonl")
    att_path = Path("logs/ritual_attestations.jsonl")

    sup = summarize_log(sup_path, limit=limit)
    fed = summarize_log(fed_path, limit=limit)

    data = {
        "support_count": sup["count"],
        "federation_count": fed["count"],
        "support_recent": sup["recent"],
        "federation_recent": fed["recent"],
        "unique_supporters": _unique_values(sup_path, "supporter"),
        "unique_witnesses": _unique_values(att_path, "user"),
    }
    print(json.dumps(data, indent=2))


def snapshot_counts() -> Dict[str, int]:
    """Return counts and unique totals for the main ledgers."""
    sup_path = Path("logs/support_log.jsonl")
    fed_path = Path("logs/federation_log.jsonl")
    att_path = Path("logs/ritual_attestations.jsonl")

    return {
        "support": summarize_log(sup_path)["count"],
        "federation": summarize_log(fed_path)["count"],
        "witness": summarize_log(att_path)["count"],
        "unique_support": _unique_values(sup_path, "supporter"),
        "unique_peers": _unique_values(fed_path, "peer"),
        "unique_witness": _unique_values(att_path, "user"),
    }


def print_snapshot_banner() -> None:
    """Print a short ledger snapshot banner."""
    c = snapshot_counts()
    print(
        "Ledger snapshot • "
        f"Support: {c['support']} ({c['unique_support']} unique) • "
        f"Federation: {c['federation']} ({c['unique_peers']} unique) • "
        f"Witness: {c['witness']} ({c['unique_witness']} unique)"
    )


def print_recap(limit: int = 3) -> None:
    """Print a recap of recent support and federation blessings."""
    sup = summarize_log(Path("logs/support_log.jsonl"), limit=limit)
    fed = summarize_log(Path("logs/federation_log.jsonl"), limit=limit)
    data = {
        "support_recent": sup["recent"],
        "federation_recent": fed["recent"],
    }
    print(json.dumps(data, indent=2))
