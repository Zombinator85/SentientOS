"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path

import argparse
import json
import os
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Dict

EXPORT_LOG = get_log_path("ceremony_exporter.jsonl", "CEREMONY_EXPORT_LOG")
EXPORT_LOG.parent.mkdir(parents=True, exist_ok=True)


def export_ceremony(src: Path, dest: Path) -> Dict[str, str]:
    with tarfile.open(dest, "w:gz") as tar:
        tar.add(src, arcname=src.name)
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "src": str(src),
        "dest": str(dest),
    }
    with EXPORT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Festival/Onboarding Ceremony Exporter")
    ap.add_argument("src")
    ap.add_argument("dest")
    args = ap.parse_args()
    entry = export_ceremony(Path(args.src), Path(args.dest))
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
