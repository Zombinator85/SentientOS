from __future__ import annotations
from logging_config import get_log_path, get_log_dir

import argparse
import datetime
import json
import os
from pathlib import Path
from typing import Dict, List

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("genesis_oracle.jsonl", "GENESIS_ORACLE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
DATA_DIR = Path(os.getenv("GENESIS_ORACLE_DATA", str(get_log_dir())))


def query_origin(obj: str) -> Dict[str, str]:
    info = {}
    for fp in DATA_DIR.glob("*.jsonl"):
        for ln in fp.read_text(encoding="utf-8").splitlines():
            if obj in ln:
                info = json.loads(ln)
                break
    entry = {"timestamp": datetime.datetime.utcnow().isoformat(), "object": obj, "info": info}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Genesis Oracle")
    ap.add_argument("--object", required=True)
    args = ap.parse_args()
    print(json.dumps(query_origin(args.object), indent=2))


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
