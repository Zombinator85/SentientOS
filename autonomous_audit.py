"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations
from logging_config import get_log_path, get_log_dir
import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
"""
Autonomous audit and recap generator for the SentientOS Cathedral.
It scans logs and ledger files for anomalies and can produce a
public-facing report with sensitive fields masked.

The log file defaults to ``logs/autonomous_audit.jsonl`` and can be
customized with the ``AUTONOMOUS_AUDIT_LOG`` environment variable.

Example:
    python autonomous_audit.py --report-dir public_reports
"""



LOG_PATH = get_log_path("autonomous_audit.jsonl", "AUTONOMOUS_AUDIT_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
PUBLIC_DIR = Path("public_reports")


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


def _mask(entry: Dict[str, Any]) -> Dict[str, Any]:
    masked = entry.copy()
    for key in ("email", "user", "agent"):
        if key in masked:
            masked[key] = "<redacted>"
    return masked


def scan_logs(log_dir: Path | None = None) -> List[Dict[str, Any]]:
    if log_dir is None:
        log_dir = get_log_dir()
    anomalies: List[Dict[str, Any]] = []
    for fp in log_dir.glob("*.jsonl"):
        for idx, line in enumerate(fp.read_text(encoding="utf-8").splitlines(), 1):
            try:
                entry = json.loads(line)
            except Exception:
                anomalies.append({"log": fp.name, "line": idx, "issue": "invalid json"})
                continue
            if "timestamp" not in entry or "action" not in entry:
                anomalies.append({"log": fp.name, "line": idx, "issue": "missing fields"})
    return anomalies


def generate_report(report_dir: Path = PUBLIC_DIR) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    anomalies = scan_logs()
    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "anomaly_count": len(anomalies),
        "anomalies": [_mask(a) for a in anomalies],
    }
    name = f"audit_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    dest = report_dir / name
    dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return dest


if __name__ == "__main__":  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description="Autonomous audit recap")
    p.add_argument("--last", type=int, default=0, help="show last N entries")
    p.add_argument(
        "--report-dir",
        default=str(PUBLIC_DIR),
        help="directory for generated reports",
    )
    args = p.parse_args()
    if args.last:
        for e in recent(args.last):
            print(json.dumps(e, indent=2))
    else:
        path = generate_report(Path(args.report_dir))
        print(str(path))
# May memory be healed and preserved.
