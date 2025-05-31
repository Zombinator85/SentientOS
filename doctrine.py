import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Paths
ROOT = Path(__file__).resolve().parent
DOCTRINE_PATH = Path(os.getenv("DOCTRINE_PATH", ROOT / "SENTIENTOS_LITURGY.txt"))
CONSENT_LOG = Path(os.getenv("DOCTRINE_CONSENT_LOG", "logs/doctrine_consent.jsonl"))
STATUS_LOG = Path(os.getenv("DOCTRINE_STATUS_LOG", "logs/doctrine_status.jsonl"))
AMEND_LOG = Path(os.getenv("DOCTRINE_AMEND_LOG", "logs/doctrine_amendments.jsonl"))
PUBLIC_LOG = Path(os.getenv("PUBLIC_RITUAL_LOG", "logs/public_rituals.jsonl"))
MASTER_CONFIG = Path(os.getenv("MASTER_CONFIG", ROOT / "config" / "master_files.json"))

for p in [CONSENT_LOG, STATUS_LOG, AMEND_LOG, PUBLIC_LOG]:
    p.parent.mkdir(parents=True, exist_ok=True)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()


def doctrine_hash() -> str:
    if not DOCTRINE_PATH.exists():
        return ""
    return _sha256(DOCTRINE_PATH)


def log_json(path: Path, obj: Dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")


def affirm(user: str) -> None:
    """Record user consent to the current doctrine."""
    entry = {"time": time.time(), "user": user, "hash": doctrine_hash()}
    log_json(CONSENT_LOG, entry)
    log_json(PUBLIC_LOG, {"time": entry["time"], "event": "affirm", "user": user})


def last_affirm_time() -> float:
    if not CONSENT_LOG.exists():
        return 0.0
    try:
        last = json.loads(CONSENT_LOG.read_text().splitlines()[-1])
        return float(last.get("time", 0.0))
    except Exception:
        return 0.0


def maybe_prompt(days: int, user: str) -> None:
    """Prompt user to re-affirm if N days have passed."""
    if time.time() - last_affirm_time() > days * 86400:
        print(DOCTRINE_PATH.read_text())
        affirm(user)


def _scan_master_files() -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if not MASTER_CONFIG.exists():
        return results
    try:
        data = json.loads(MASTER_CONFIG.read_text())
    except Exception:
        return results
    for file, digest in data.items():
        fp = Path(file)
        if not fp.is_absolute():
            fp = ROOT / fp
        info: Dict[str, Any] = {"file": str(file)}
        if not fp.exists():
            info["status"] = "missing"
        else:
            actual = _sha256(fp)
            perm = oct(fp.stat().st_mode & 0o777)
            info["permissions"] = perm
            if actual != digest:
                info["status"] = "hash_mismatch"
            else:
                info["status"] = "ok"
        results.append(info)
    return results


def integrity_report() -> Dict[str, Any]:
    items = _scan_master_files()
    ok = all(i.get("status") == "ok" for i in items)
    report = {"time": time.time(), "ok": ok, "items": items}
    log_json(STATUS_LOG, report)
    log_json(PUBLIC_LOG, {"time": report["time"], "event": "status", "ok": ok})
    return report


def amend(proposal: str, user: str, vote: Optional[str] = None) -> str:
    """Record a doctrine amendment proposal or vote."""
    entry: Dict[str, Any] = {
        "time": time.time(),
        "user": user,
        "hash": doctrine_hash(),
    }
    if vote:
        entry.update({"event": "vote", "proposal": proposal, "value": vote})
    else:
        entry.update({"event": "propose", "proposal": proposal})
    log_json(AMEND_LOG, entry)
    log_json(PUBLIC_LOG, {k: entry[k] for k in ("time", "event", "proposal", "user")})
    return json.dumps(entry)


def history(n: int = 20) -> List[Dict[str, Any]]:
    if not AMEND_LOG.exists():
        return []
    lines = AMEND_LOG.read_text().splitlines()[-n:]
    out: List[Dict[str, Any]] = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


CLI_DESC = "Doctrine management and ritual utilities"

def main() -> None:
    p = argparse.ArgumentParser(description=CLI_DESC)
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("show")

    a_aff = sub.add_parser("affirm")
    a_aff.add_argument("--user", default=os.getenv("USER", "anon"))

    sub.add_parser("report")

    a_amend = sub.add_parser("amend")
    a_amend.add_argument("proposal")
    a_amend.add_argument("--user", default=os.getenv("USER", "anon"))
    a_amend.add_argument("--vote")

    a_hist = sub.add_parser("history")
    a_hist.add_argument("--last", type=int, default=10)

    args = p.parse_args()
    if args.cmd == "show":
        print(DOCTRINE_PATH.read_text())
    elif args.cmd == "affirm":
        affirm(args.user)
        print("affirmed")
    elif args.cmd == "report":
        rep = integrity_report()
        print(json.dumps(rep, indent=2))
    elif args.cmd == "amend":
        out = amend(args.proposal, args.user, args.vote)
        print(out)
    elif args.cmd == "history":
        for entry in history(args.last):
            print(json.dumps(entry))
    else:
        p.print_help()


if __name__ == "__main__":  # pragma: no cover
    main()
