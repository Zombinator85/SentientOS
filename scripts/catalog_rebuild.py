from __future__ import annotations

import json
import os
from pathlib import Path

from sentientos.artifact_catalog import rebuild_catalog_from_disk


def main() -> int:
    if os.getenv("SENTIENTOS_ALLOW_CATALOG_REBUILD", "0") != "1":
        print(json.dumps({"status": "blocked", "reason": "set SENTIENTOS_ALLOW_CATALOG_REBUILD=1"}, sort_keys=True))
        return 2
    result = rebuild_catalog_from_disk(Path.cwd().resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
