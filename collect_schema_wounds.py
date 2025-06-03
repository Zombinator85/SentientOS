from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from typing import Dict
from admin_utils import require_admin_banner
from fix_audit_schema import KNOWN_KEYS
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.


def analyze() -> Dict[str, int]:
    log_dir = get_log_path("dummy").parent
    counter: Counter[str] = Counter()
    for wound_file in log_dir.glob("*.wounds"):
        for line in wound_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except Exception:
                counter["malformed"] += 1
                continue
            if not isinstance(entry, dict):
                counter["not_dict"] += 1
                continue
            for key in KNOWN_KEYS:
                if key not in entry:
                    counter[f"missing:{key}"] += 1
            for key in entry:
                if key not in KNOWN_KEYS:
                    counter[f"unknown:{key}"] += 1
    return dict(counter)


def main() -> None:
    stats = analyze()
    out_path = Path("docs/SCHEMA_WOUND_STATS.json")
    out_path.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
