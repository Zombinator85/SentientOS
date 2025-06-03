from __future__ import annotations
import datetime
from logging_config import get_log_dir
from pathlib import Path

from admin_utils import require_admin_banner
import verify_audits as va

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

LOG_DIR = get_log_dir()
AUDIT_DOC = Path("docs/AUDIT_LOG.md")


def run_audit() -> None:
    results, percent, _ = va.verify_audits(quarantine=True, directory=LOG_DIR)
    date = datetime.date.today().isoformat()
    summary = f"{percent:.1f}% valid"
    row = f"| {date} | {summary} |"
    if AUDIT_DOC.exists():
        lines = AUDIT_DOC.read_text(encoding="utf-8").splitlines()
    else:
        lines = ["# Monthly Audit Log", "", "| Date | Summary |", "|------|---------|"]
    lines.append(row)
    AUDIT_DOC.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover - manual
    require_admin_banner()
    run_audit()
