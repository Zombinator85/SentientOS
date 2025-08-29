from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import json
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from queue import Queue
from typing import Tuple

import yaml

CODEX_LOG = Path("/daemon/logs/codex.jsonl")
CODEX_PATCH_DIR = Path("/glow/codex_suggestions/")
CONFIG_FILE = Path("/vow/config.yaml")
DEFAULT_CONFIG = {
    "codex_auto_apply": False,
    "codex_interval": 3600,
    "codex_confirm_patterns": ["/vow/", "NEWLEGACY.txt"],
}
try:
    CONFIG = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
    if not isinstance(CONFIG, dict):
        CONFIG = {}
except FileNotFoundError:
    CONFIG = {}
CONFIG = {**DEFAULT_CONFIG, **CONFIG}

CODEX_AUTO_APPLY = bool(CONFIG.get("codex_auto_apply", False))
CODEX_INTERVAL = int(CONFIG.get("codex_interval", 3600))
CODEX_CONFIRM_PATTERNS = CONFIG.get(
    "codex_confirm_patterns", ["/vow/", "NEWLEGACY.txt"]
)


def run_diagnostics() -> Tuple[bool, str]:
    """Run pytest and mypy, returning (all_passed, summary)."""
    results: list[str] = []
    all_passed = True
    tests = [
        ["pytest", "-q"],
        ["mypy", "--ignore-missing-imports", "."],
    ]
    for cmd in tests:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            all_passed = False
            results.append(proc.stdout + proc.stderr)
    summary = "\n".join(r.strip() for r in results if r.strip())
    return all_passed, summary


def parse_diff_files(diff: str) -> list[str]:
    files: list[str] = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            files.append(line[6:])
    return files


def is_safe(files: list[str]) -> bool:
    return not any(
        any(pattern in f for pattern in CODEX_CONFIRM_PATTERNS) for f in files
    )


def apply_patch(diff: str) -> bool:
    proc = subprocess.run(["patch", "-p0"], input=diff, text=True)
    return proc.returncode == 0


def log_activity(entry: dict) -> None:
    CODEX_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CODEX_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def run_once(ledger_queue: Queue) -> None:
    passed, summary = run_diagnostics()
    if passed:
        return

    prompt = (
        "Fix the following issues in SentientOS. Pytest/mypy outputs:\n"
        f"{summary}\n"
        "Please resolve so all tests and type checks pass. Output a unified diff."
    )
    proc = subprocess.run(["codex", "exec", prompt], capture_output=True, text=True)
    diff_output = proc.stdout
    CODEX_PATCH_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    patch_path = CODEX_PATCH_DIR / f"patch_{timestamp}.diff"
    patch_path.write_text(diff_output, encoding="utf-8")

    files_changed = parse_diff_files(diff_output)
    verified = False

    if CODEX_AUTO_APPLY and files_changed and is_safe(files_changed):
        if apply_patch(diff_output):
            passed, _ = run_diagnostics()
            if passed:
                subprocess.run(["git", "add", "-A"], check=False)
                subprocess.run([
                    "git",
                    "commit",
                    "-m",
                    "[codex:self_repair]",
                ],
                    check=False,
                )
                verified = True

    entry = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "prompt": prompt,
        "files_changed": files_changed,
        "verified": verified,
        "codex_patch": patch_path.as_posix().lstrip("/"),
    }
    log_activity(entry)
    ledger_queue.put(
        {
            "event": "self_repair",
            "ts": entry["ts"],
            "files_changed": files_changed,
            "verified": verified,
            "codex_patch": entry["codex_patch"],
        }
    )


def run_loop(stop: threading.Event, ledger_queue: Queue) -> None:
    while not stop.is_set():
        try:
            run_once(ledger_queue)
        except Exception as exc:  # pragma: no cover - best effort logging
            log_activity({
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "error": str(exc),
                "files_changed": [],
                "verified": False,
                "codex_patch": "",
            })
        if stop.wait(CODEX_INTERVAL):
            break
