from logging_config import get_log_path
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

LOG_PATH = get_log_path("autonomous_audit.jsonl", "AUTONOMOUS_AUDIT_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_entry(
    action: str,
    rationale: str,
    *,
    source: Dict[str, Any] | None = None,
    memory: List[str] | None = None,
    expected: str | None = None,
    why_chain: List[str] | None = None,
    agent: str = "auto",
) -> None:
    """Write an autonomous audit entry."""
    entry = {
        "timestamp": time.time(),
        "action": action,
        "rationale": rationale,
        "source": source or {},
        "memory": memory or [],
        "expected": expected or "",
        "why_chain": why_chain or [],
        "agent": agent,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def recent(last: int = 10) -> List[Dict[str, Any]]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-last:]
    out: List[Dict[str, Any]] = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


if __name__ == "__main__":  # pragma: no cover - CLI
    import argparse

    require_admin_banner()
    p = argparse.ArgumentParser(description="Recent autonomous audit entries")
    p.add_argument("--last", type=int, default=10)
    args = p.parse_args()
    for e in recent(args.last):
        print(json.dumps(e, indent=2))
