from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details.

Scan audit logs for schema drift and heal missing fields."""

KNOWN_KEYS = {"timestamp", "peer", "email", "message", "ritual", "data", "supporter", "amount"}
DEFAULTS: Dict[str, object] = {"data": {}}


def process_log(path: Path) -> Dict[str, int]:
    fixed = 0
    flagged = 0
    untouched = 0
    if not path.exists():
        return {"fixed": fixed, "flagged": flagged, "untouched": untouched}

    wounds_path = path.with_suffix(path.suffix + ".wounds")
    new_lines: List[str] = []
    flagged_lines: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if not isinstance(entry, dict):
                raise ValueError("not dict")
        except Exception:
            flagged_lines.append(line)
            flagged += 1
            continue

        unknown = [k for k in entry if k not in KNOWN_KEYS]
        if unknown:
            flagged_lines.append(line)
            flagged += 1
            continue

        changed = False
        for key, default in DEFAULTS.items():
            if key not in entry:
                entry[key] = default
                changed = True
        if changed:
            entry["auto_migrated"] = True
            fixed += 1
        else:
            untouched += 1
        new_lines.append(json.dumps(entry, ensure_ascii=False))

    if flagged_lines:
        wounds_path.write_text("\n".join(flagged_lines) + "\n", encoding="utf-8")
    path.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")
    return {"fixed": fixed, "flagged": flagged, "untouched": untouched}


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    logs_dir = Path("logs")
    totals = {"fixed": 0, "flagged": 0, "untouched": 0}
    for log_file in logs_dir.glob("*.jsonl"):
        stats = process_log(log_file)
        for k in totals:
            totals[k] += stats[k]
    print("Fixed: {fixed} | Flagged: {flagged} | Untouched: {untouched}".format(**totals))


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
