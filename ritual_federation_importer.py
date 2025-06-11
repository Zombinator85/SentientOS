from logging_config import get_log_path
import argparse
import json
from pathlib import Path
from typing import Dict

from ledger import _append

from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
LOG_PATHS = {
    "confession": get_log_path("confessional_log.jsonl"),
    "blessing": get_log_path("support_log.jsonl"),
    "federation": get_log_path("federation_log.jsonl"),
    "forgiveness": get_log_path("forgiveness_ledger.jsonl"),
    "heresy": get_log_path("heresy_log.jsonl"),
}


def import_recap(path: Path, source: str = "") -> int:
    count = 0
    data = []
    text = path.read_text(encoding="utf-8")
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            data = obj
    except Exception:
        for line in text.splitlines():
            try:
                data.append(json.loads(line))
            except Exception:
                continue
    for entry in data:
        kind = entry.get("_kind") or entry.get("kind")
        if not kind or kind not in LOG_PATHS:
            continue
        entry["source"] = source or str(path)
        _append(LOG_PATHS[kind], entry)
        count += 1
    return count


def main() -> None:
    ap = argparse.ArgumentParser(description="Import federation recap")
    ap.add_argument("file", type=Path)
    ap.add_argument("--source", default="")
    args = ap.parse_args()
    print(json.dumps({"imported": import_recap(args.file, args.source)}))


if __name__ == "__main__":
    main()
