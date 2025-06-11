from cathedral_const import PUBLIC_LOG, log_json as cathedral_log_json
from admin_utils import require_admin_banner, require_lumos_approval
from logging_config import get_log_path
import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Paths
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
ROOT = Path(__file__).resolve().parent
DOCTRINE_PATH = Path(os.getenv("DOCTRINE_PATH", ROOT / "SENTIENTOS_LITURGY.txt"))
CONSENT_LOG = get_log_path("doctrine_consent.jsonl", "DOCTRINE_CONSENT_LOG")
STATUS_LOG = get_log_path("doctrine_status.jsonl", "DOCTRINE_STATUS_LOG")
AMEND_LOG = get_log_path("doctrine_amendments.jsonl", "DOCTRINE_AMEND_LOG")
MASTER_CONFIG = Path(os.getenv("MASTER_CONFIG", ROOT / "config" / "master_files.json"))
SIGNATURE_LOG = get_log_path("ritual_signatures.jsonl", "DOCTRINE_SIGNATURE_LOG")

for p in [CONSENT_LOG, STATUS_LOG, AMEND_LOG, PUBLIC_LOG, SIGNATURE_LOG]:
    p.parent.mkdir(parents=True, exist_ok=True)



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
    try:
        with path.open("a"):
            pass
        writable = True
    except PermissionError:
        writable = False
    if not writable:
        return True
    try:
        return (path.stat().st_mode & 0o222) == 0
    except Exception:
        return False


def verify_file(path: Path, digest: str) -> bool:
    """Return True if file content matches digest and is immutable."""
    if not path.exists():
        return False
    if _sha256(path) != digest:
        return False
    return _is_immutable(path)


def doctrine_hash() -> str:
    if not DOCTRINE_PATH.exists():
        return ""
    return _sha256(DOCTRINE_PATH)


def log_json(path: Path, obj: Dict[str, Any]) -> None:
    cathedral_log_json(path, obj)


def consent_history(user: Optional[str] = None, n: int = 20) -> List[Dict[str, Any]]:
    if not CONSENT_LOG.exists():
        return []
    lines = CONSENT_LOG.read_text().splitlines()
    if user:
        lines = [ln for ln in lines if f'"user": "{user}"' in ln]
    lines = lines[-n:]
    out: List[Dict[str, Any]] = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def consent_count(user: str) -> int:
    if not CONSENT_LOG.exists():
        return 0
    lines = [ln for ln in CONSENT_LOG.read_text().splitlines() if f'"user": "{user}"' in ln]
    return len(lines)


def affirm(user: str) -> None:
    """Record user consent to the current doctrine."""
    entry = {"time": time.time(), "user": user, "hash": doctrine_hash()}
    log_json(CONSENT_LOG, entry)
    log_json(PUBLIC_LOG, {"time": entry["time"], "event": "affirm", "user": user})


def capture_signature(user: str, signature: str) -> None:
    """Store ritual signature for user."""
    entry = {
        "time": time.time(),
        "user": user,
        "signature": signature,
    }
    log_json(SIGNATURE_LOG, entry)


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


def maybe_prompt_login(n: int, user: str) -> None:
    """Prompt every Nth login or when doctrine hash changes."""
    hist = consent_history(user)
    if not hist or len(hist) % n == 0 or hist[-1].get("hash") != doctrine_hash():
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
            perm = oct(fp.stat().st_mode & 0o777)
            info["permissions"] = perm
            if verify_file(fp, digest):
                info["status"] = "ok"
            elif _sha256(fp) != digest:
                info["status"] = "hash_mismatch"
            elif not _is_immutable(fp):
                info["status"] = "mutable"
            else:
                info["status"] = "unknown"
        results.append(info)
    return results


def integrity_report() -> Dict[str, Any]:
    items = _scan_master_files()
    ok = all(i.get("status") == "ok" for i in items)
    report = {"time": time.time(), "ok": ok, "items": items}
    log_json(STATUS_LOG, report)
    log_json(PUBLIC_LOG, {"time": report["time"], "event": "status", "ok": ok})
    return report


def enforce_runtime() -> None:
    """Exit if master files are modified or missing."""
    rep = integrity_report()
    if not rep.get("ok"):
        raise SystemExit("Doctrine violation detected")


try:
    from watchdog.observers import Observer  # type: ignore  # optional file watcher
    from watchdog.events import FileSystemEventHandler  # type: ignore  # optional file watcher
except Exception:  # pragma: no cover - optional dependency
    Observer = None  # type: ignore  # watchdog not installed
    FileSystemEventHandler = object  # type: ignore  # placeholder


def start_watchdog(callback: Callable[[str], None]) -> Optional[object]:
    """Watch master files for changes and invoke callback."""
    if Observer is None:
        return None

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event) -> None:  # type: ignore[override]  # watchdog callback
            callback(event.src_path)

    obs = Observer()
    for file in _scan_master_files():
        fp = Path(file["file"])
        if not fp.is_absolute():
            fp = ROOT / fp
        if fp.exists():
            obs.schedule(Handler(), str(fp.parent), recursive=False)
    obs.start()
    return obs


def watch_daemon() -> None:
    """Run a watchdog daemon printing/logging mutations."""
    def notify(path: str) -> None:
        msg = f"master file changed: {path}"
        print(msg)
        log_json(PUBLIC_LOG, {"time": time.time(), "event": "watch", "path": path})

    obs = start_watchdog(notify)
    if obs is None:
        print("watchdog not available")
        return
    print("Watching master files... Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        obs.stop()
        obs.join()


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


def public_feed(n: int = 5) -> List[Dict[str, Any]]:
    if not PUBLIC_LOG.exists():
        return []
    lines = PUBLIC_LOG.read_text().splitlines()[-n:]
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
    p.add_argument("--watch", action="store_true", help="Watch master files for changes")
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

    if args.watch:
        watch_daemon()


if __name__ == "__main__":  # pragma: no cover
    main()
