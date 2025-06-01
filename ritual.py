import os
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple
import argparse
from datetime import datetime
import getpass
import doctrine  # Assume doctrine.py is importable
import relationship_log as rl
import headless_log as hl

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
    if os.getenv("SENTIENTOS_HEADLESS") == "1" or not sys.stdin.isatty():
        hl.log_skip("liturgy_prompt", "headless or non-interactive")
        return
    pending = hl.review_pending()
    if pending:
        print("Pending ritual notices:")
        for p in pending:
            print(f"- {p['event']}: {p.get('reason','')}")
    digest = _sha256(LITURGY_FILE)
    if LITURGY_LOG.exists() and digest in LITURGY_LOG.read_text():
        return
    # Display full doctrine
    print(LITURGY_FILE.read_text())
    if README_ROMANCE.exists():
        print(README_ROMANCE.read_text())
    ans = input("Type 'I AGREE' to continue: ")
    if ans.strip() != "I AGREE":
        _log_refusal([str(LITURGY_FILE)], "liturgy not accepted")
        raise SystemExit(1)
    _log_acceptance(digest)
    # record in doctrine log and relationship log
    doctrine.affirm(getpass.getuser())
    rl.log_event("affirmation", getpass.getuser())


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
        # Check file presence and hash
        if not fp.exists() or _sha256(fp) != digest:
            missing.append(str(fp))
        # Check for immutability if enabled
        elif os.getenv("MASTER_CHECK_IMMUTABLE", "1") == "1" and not _is_immutable(fp):
            missing.append(f"{fp}:mutable")

    # Always write a doctrine integrity report (using doctrine.py utility)
    doctrine.integrity_report()

    return not missing, missing


def enforce_or_exit() -> None:
    """Check doctrine and exit if violated."""
    ok, missing = check_master_files()
    if not ok:
        print("Ritual Refusal Mode. Missing or altered master files:", ", ".join(missing))
        raise SystemExit(1)


def confirm_disruptive(action: str, summary: str) -> None:
    """Require multi-step confirmation for destructive actions."""
    if os.getenv("SENTIENTOS_HEADLESS") == "1" or not sys.stdin.isatty():
        hl.log_skip(action, "headless or non-interactive")
        return
    print(f"Ritual guidance: {summary}")
    ans = input(f"Type 'YES' to proceed with {action}: ")
    if ans.strip() != "YES":
        raise SystemExit("Action cancelled by doctrine")


def _cli_affirm(args: argparse.Namespace) -> None:
    user = args.user or os.getenv("USER", "anon")
    doctrine.affirm(user)
    doctrine.capture_signature(user, args.signature)
    print("affirmed")


def _cli_bless(args: argparse.Namespace) -> None:
    name = args.name or input("Name: ")
    message = args.message or input("Blessing: ")
    amount = args.amount or ""
    import support_log as sl

    entry = sl.add(name, message, amount)
    print(json.dumps(entry))


def _cli_status(args: argparse.Namespace) -> None:
    rep = doctrine.integrity_report()
    print(json.dumps(rep, indent=2))


def _cli_logs(args: argparse.Namespace) -> None:
    feed = doctrine.public_feed(args.last)
    for entry in feed:
        print(json.dumps(entry))


def main() -> None:
    ap = argparse.ArgumentParser(prog="ritual")
    sub = ap.add_subparsers(dest="cmd")

    aff = sub.add_parser("affirm")
    aff.add_argument("--signature", required=True)
    aff.add_argument("--user")
    aff.set_defaults(func=_cli_affirm)

    bl = sub.add_parser("bless")
    bl.add_argument("--name")
    bl.add_argument("--message")
    bl.add_argument("--amount", default="")
    bl.set_defaults(func=_cli_bless)

    st = sub.add_parser("status")
    st.add_argument("--doctrine", action="store_true")
    st.set_defaults(func=_cli_status)

    lg = sub.add_parser("logs")
    lg.add_argument("--last", type=int, default=5)
    lg.set_defaults(func=_cli_logs)

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover
    main()
