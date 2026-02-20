from __future__ import annotations

import json
from pathlib import Path
import sys

from sentientos.doctrine_identity import verify_doctrine_identity


def main() -> int:
    ok, payload = verify_doctrine_identity(Path.cwd())
    print(json.dumps(payload, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
