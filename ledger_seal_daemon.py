"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from logging_config import get_log_path
# Cryptographic Ledger Seal & Backup Daemon


SEAL_LOG = get_log_path("ledger_seal.jsonl", "LEDGER_SEAL_LOG")
SEAL_LOG.parent.mkdir(parents=True, exist_ok=True)
BACKUP_DIR = Path(os.getenv("LEDGER_BACKUP_DIR", "backup"))
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def seal_file(path: Path) -> dict:
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "file": str(path),
        "sha256": digest,
    }
    with SEAL_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    backup = BACKUP_DIR / path.name
    shutil.copy2(path, backup)
    return entry


def verify_file(path: Path, digest: str) -> bool:
    return hashlib.sha256(path.read_bytes()).hexdigest() == digest


def cli() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Ledger seal daemon")
    ap.add_argument("file")
    ap.add_argument("--verify", help="Digest to verify")
    args = ap.parse_args()
    fp = Path(args.file)
    if args.verify:
        ok = verify_file(fp, args.verify)
        print(json.dumps({"verified": ok}, indent=2))
    else:
        entry = seal_file(fp)
        print(json.dumps(entry, indent=2))


if __name__ == "__main__":  # pragma: no cover
    cli()
