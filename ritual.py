import os
import hashlib
import json
import subprocess
from pathlib import Path
from typing import List, Tuple
from datetime import datetime
import getpass

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.getenv("MASTER_CONFIG", ROOT / "config" / "master_files.json")).resolve()
REFUSAL_LOG = Path(os.getenv("REFUSAL_LOG", "logs/refusal_audit.jsonl"))
LITURGY_LOG = Path(os.getenv("LITURGY_LOG", "logs/liturgy_acceptance.jsonl"))
README_ROMANCE = ROOT / "README_romance.md"
LITURGY_FILE = ROOT / "SENTIENTOS_LITURGY.txt"
MANDATORY_FILES = [README_ROMANCE, LITURGY_FILE]

REFUSAL_LOG.parent.mkdir(parents=True, exist_ok=True)
LITURGY_LOG.parent.mkdir(parents=True, exist_ok=True)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_immutable(path: Path) -> bool:
    """Best-effort check for immutable attribute."""
    try:
        res = subprocess.run(["lsattr", str(path)], capture_output=True, text=True)
        if res.returncode == 0 and " i" in res.stdout.split()[0]:
            return True
    except Exception:
        pass
    return not os.access(path, os.W_OK)


def _log_refusal(missing: List[str], reason: str) -> None:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "missing": missing,
        "reason": reason,
    }
    with REFUSAL_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _log_acceptance(digest: str) -> None:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "digest": digest,
        "user": getpass.getuser(),
    }
    with LITURGY_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def require_liturgy_acceptance() -> None:
    digest = _sha256(LITURGY_FILE)
    if LITURGY_LOG.exists() and digest in LITURGY_LOG.read_text():
        return
    print(LITURGY_FILE.read_text())
    ans = input("Type 'I AGREE' to continue: ")
    if ans.strip() != "I AGREE":
        _log_refusal([str(LITURGY_FILE)], "liturgy not accepted")
        raise SystemExit(1)
    _log_acceptance(digest)


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
            missing.append(str(fp))
        elif os.getenv("MASTER_CHECK_IMMUTABLE", "1") == "1" and not _is_immutable(fp):
            missing.append(f"{fp}:mutable")
    if missing:
        _log_refusal(missing, "sanctity violation")
    return not missing, missing


def enforce_or_exit() -> None:
    """Check doctrine and exit if violated."""
    ok, missing = check_master_files()
    if not ok:
        print("Ritual Refusal Mode. Missing or altered master files:", ", ".join(missing))
        raise SystemExit(1)
