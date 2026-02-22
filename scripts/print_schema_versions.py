from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sentientos.schema_registry import LATEST_VERSIONS, MIN_SUPPORTED_VERSIONS


def main() -> int:
    rows = []
    for name in sorted(LATEST_VERSIONS):
        rows.append({
            "schema": name,
            "latest_version": LATEST_VERSIONS[name],
            "min_supported_version": MIN_SUPPORTED_VERSIONS.get(name, LATEST_VERSIONS[name]),
        })
    print(json.dumps({"schemas": rows}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
