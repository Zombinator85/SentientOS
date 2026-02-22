from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sentientos.artifact_retention import RetentionPolicy, run_retention


def main() -> int:
    root = Path.cwd()
    result = run_retention(root, policy=RetentionPolicy.from_env(), now=datetime.now(timezone.utc))
    payload = result.to_dict()
    out = root / "glow/forge/retention" / f"retention_run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
