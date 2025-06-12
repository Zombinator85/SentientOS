"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import argparse
import json
from datetime import datetime
from pathlib import Path

LOGS = [
    ("blessing", get_log_path("support_log.jsonl")),
    ("confession", get_log_path("confessional_log.jsonl")),
    ("forgiveness", get_log_path("forgiveness_ledger.jsonl")),
    ("federation", get_log_path("federation_log.jsonl")),
]


def _load(path: Path):
    if not path.exists():
        return []
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def compile_changelog() -> Path:
    lines = ["# CATHEDRAL_HISTORY"]
    by_day = {}
    for name, path in LOGS:
        for e in _load(path):
            day = str(e.get("timestamp", "")).split("T")[0]
            by_day.setdefault(day, []).append((name, e))
    for day in sorted(by_day):
        lines.append(f"\n## {day}")
        for name, e in by_day[day]:
            lines.append(f"* **{name}** {json.dumps(e, ensure_ascii=False)}")
    out = Path("CATHEDRAL_HISTORY.md")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Liturgical changelog compiler")
    ap.add_argument("--out")
    args = ap.parse_args()
    path = compile_changelog()
    if args.out:
        Path(args.out).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(args.out)
    else:
        print(path)


if __name__ == "__main__":
    main()
