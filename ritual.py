import os
import hashlib
import json
from pathlib import Path
from typing import List, Tuple
import doctrine

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.getenv("MASTER_CONFIG", ROOT / "config" / "master_files.json")).resolve()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()


def check_master_files() -> Tuple[bool, List[str]]:
    """Return (ok, missing_or_changed)."""
    if os.getenv("MASTER_ENFORCE") != "1":
        return True, []
    if not CONFIG_PATH.exists():
        return True, []
    data = json.loads(CONFIG_PATH.read_text())
    missing: List[str] = []
    for p, digest in data.items():
        fp = Path(p)
        if not fp.is_absolute():
            fp = (ROOT / fp).resolve()
        if not fp.exists() or _sha256(fp) != digest:
            missing.append(p)

    # Write extended doctrine integrity report
    doctrine.integrity_report()

    return not missing, missing
