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
import re

CODEX_LOG = Path("/daemon/logs/codex.jsonl")
# Directory for storing Codex patches
CODEX_PATCH_DIR = Path("/glow/codex_suggestions/")

# Config handling ----------------------------------------------------------
CONFIG_FILE = Path("/vow/config.yaml")
DEFAULT_CONFIG = {
    "codex_auto_apply": False,
    "codex_interval": 3600,
    "codex_confirm_patterns": ["/vow/", "NEWLEGACY.txt"],
    # Maximum Codex fix attempts per cycle
    "codex_max_iterations": 1,
    # Focus for diagnostics: "pytest" or "mypy"
    "codex_focus": "pytest",
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
CODEX_MAX_ITERATIONS = int(CONFIG.get("codex_max_iterations", 1))
CODEX_FOCUS = str(CONFIG.get("codex_focus", "pytest"))


def run_diagnostics() -> Tuple[bool, str, int]:
    """Run selected diagnostics.

    Returns a tuple of ``(all_passed, summary, error_count)`` where ``error_count``
    is the number of failing tests or type errors depending on
    :data:`CODEX_FOCUS`.
    """

    if CODEX_FOCUS == "mypy":
        cmd = ["mypy", "--ignore-missing-imports", "."]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        output = proc.stdout + proc.stderr
        match = re.search(r"Found (\d+) errors?", output)
        errors = int(match.group(1)) if match else 0
        return proc.returncode == 0, output, errors

    # Default: pytest focus
    cmd = ["pytest", "-q"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    output = proc.stdout + proc.stderr
    match = re.search(r"(\d+) failed", output)
    errors = int(match.group(1)) if match else 0
    return proc.returncode == 0, output, errors


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


def run_once(ledger_queue: Queue) -> dict | None:
    """Attempt to heal the repository once.

    Returns the ledger entry if a repair was attempted, otherwise ``None``.
    """

    passed, summary, errors_before = run_diagnostics()
    if passed:
        return None

    files_changed: set[str] = set()
    patch_paths: list[str] = []
    verified: bool | str = False
    outcome = "fail"
    attempts = 0
    current_summary = summary
    previous_errors = errors_before

    for attempt in range(1, CODEX_MAX_ITERATIONS + 1):
        attempts = attempt
        prompt = (
            "Fix the following issues in SentientOS. Pytest/mypy outputs:\n"
            f"{current_summary}\n"
            "Please resolve so all tests and type checks pass. Output a unified diff."
        )
        proc = subprocess.run(["codex", "exec", prompt], capture_output=True, text=True)
        diff_output = proc.stdout
        CODEX_PATCH_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        patch_path = CODEX_PATCH_DIR / f"patch_{timestamp}.diff"
        patch_path.write_text(diff_output, encoding="utf-8")
        patch_paths.append(patch_path.as_posix().lstrip("/"))

        files_changed.update(parse_diff_files(diff_output))

        if CODEX_AUTO_APPLY and files_changed and is_safe(list(files_changed)):
            if apply_patch(diff_output):
                passed, current_summary, current_errors = run_diagnostics()
                if passed:
                    subprocess.run(["git", "add", "-A"], check=False)
                    subprocess.run(
                        ["git", "commit", "-m", "[codex:self_repair]"],
                        check=False,
                    )
                    verified = True
                    outcome = "success"
                    break
                if CODEX_FOCUS == "mypy" and current_errors < previous_errors:
                    verified = "partial"
                    previous_errors = current_errors
                    outcome = "partial"
                else:
                    previous_errors = current_errors
        else:
            # Could not apply automatically; break out
            break

    entry = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "prompt": prompt,
        "files_changed": list(files_changed),
        "verified": verified,
        "codex_patch": patch_paths[-1] if patch_paths else "",
        "iterations": attempts,
        "target": CODEX_FOCUS,
        "outcome": outcome,
    }
    log_activity(entry)
    event_name = "self_repair" if outcome != "fail" else "self_repair_failed"
    ledger_entry = {**entry, "event": event_name}
    ledger_queue.put(ledger_entry)
    return ledger_entry


def run_loop(stop: threading.Event, ledger_queue: Queue) -> None:
    codex_runs = 0
    verified_repairs = 0
    failures = 0
    while not stop.is_set():
        try:
            result = run_once(ledger_queue)
            if result:
                codex_runs += 1
                if result["outcome"] == "success":
                    verified_repairs += 1
                elif result["outcome"] == "fail":
                    failures += 1
        except Exception as exc:  # pragma: no cover - best effort logging
            log_activity({
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "error": str(exc),
                "files_changed": [],
                "verified": False,
                "codex_patch": "",
                "iterations": 0,
                "target": CODEX_FOCUS,
                "outcome": "fail",
            })
            failures += 1
        if stop.wait(CODEX_INTERVAL):
            break

    ledger_queue.put(
        {
            "event": "codex_summary",
            "codex_runs": codex_runs,
            "verified_repairs": verified_repairs,
            "failures": failures,
        }
    )
