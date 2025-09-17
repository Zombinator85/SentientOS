from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import json
import logging
import subprocess
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from queue import Queue
from typing import Tuple

import yaml
import re
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import DiffLexer
import urllib.request

from sentientos.daemons import pulse_bus, pulse_federation

from daemon.cpu_ram_daemon import run_loop as cpu_ram_daemon
CODEX_LOG = Path("/daemon/logs/codex.jsonl")
# Directory for storing Codex suggestion patches
CODEX_SUGGEST_DIR = Path("/glow/codex_suggestions/")
CODEX_PATCH_DIR = CODEX_SUGGEST_DIR  # backward compatibility
CODEX_SESSION_FILE = Path("/daemon/logs/codex_session.json")
CODEX_REQUEST_DIR = Path("/glow/codex_requests/")
CODEX_REASONING_DIR = Path("/daemon/logs/codex_reasoning/")

PRIVILEGED_PATTERNS = ["/vow/", "NEWLEGACY.txt", "init.py", "privilege.py"]

logger = logging.getLogger(__name__)

FEDERATION_REPLAY_MINUTES = 15

# Config handling ----------------------------------------------------------
CONFIG_FILE = Path("/vow/config.yaml")
DEFAULT_CONFIG = {
    "codex_auto_apply": False,
    "codex_interval": 3600,
    "codex_confirm_patterns": ["/vow/", "NEWLEGACY.txt", "init.py", "privilege.py"],
    # Maximum Codex fix attempts per cycle
    "codex_max_iterations": 1,
    # Focus for diagnostics: "pytest" or "mypy"
    "codex_focus": "pytest",
    # Autonomy mode: observe, repair, full, or expand
    "codex_mode": "observe",
    # Notification targets for verified repairs
    "codex_notify": [],
    # Resource thresholds
    "cpu_threshold": 90,
    "ram_threshold": 90,
    # Offload behavior: none, log_only, auto
    "offload_policy": "log_only",
    # Federation propagation defaults
    "federation_enabled": False,
    "federation_peers": [],
}
try:
    safe_load = yaml.safe_load  # type: ignore[attr-defined]
except AttributeError:
    CONFIG = {}
else:
    try:
        CONFIG = safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
        if not isinstance(CONFIG, dict):
            CONFIG = {}
    except FileNotFoundError:
        CONFIG = {}
    except Exception:  # pragma: no cover - malformed config treated as empty
        CONFIG = {}
CONFIG = {**DEFAULT_CONFIG, **CONFIG}
CODEX_MODE = str(CONFIG.get("codex_mode", "observe")).lower()
CODEX_INTERVAL = int(CONFIG.get("codex_interval", 3600))
CODEX_CONFIRM_PATTERNS = CONFIG.get(
    "codex_confirm_patterns", ["/vow/", "NEWLEGACY.txt", "init.py", "privilege.py"]
)
CODEX_MAX_ITERATIONS = int(CONFIG.get("codex_max_iterations", 1))
CODEX_FOCUS = str(CONFIG.get("codex_focus", "pytest"))
CODEX_AUTO_APPLY = CODEX_MODE in {"repair", "full"}
RUN_CODEX = CODEX_MODE in {"repair", "full", "expand"}
CODEX_NOTIFY = CONFIG.get("codex_notify", [])
FEDERATION_ENABLED = bool(CONFIG.get("federation_enabled", False))
FEDERATION_PEERS = CONFIG.get("federation_peers", [])

pulse_federation.configure(enabled=FEDERATION_ENABLED, peers=FEDERATION_PEERS)

CRITICAL_PULSE_EVENTS = {"enforcement", "resync_required", "integrity_violation"}
_SELF_REPAIR_LOCK = threading.Lock()


class _CriticalFailureMonitor:
    def __init__(self) -> None:
        self._threshold = 3
        self._window = timedelta(minutes=5)
        self._cooldown = timedelta(minutes=5)
        self._events: dict[tuple[str, str], deque[datetime]] = defaultdict(deque)
        self._last_request: dict[tuple[str, str], datetime] = {}

    def reset(self) -> None:
        self._events.clear()
        self._last_request.clear()

    def record(self, event: dict[str, object]) -> None:
        priority = str(event.get("priority", "info")).lower()
        if priority != "critical":
            return

        source = str(event.get("source_daemon", "")).strip()
        if not source or source in {"codex", "daemon_manager"}:
            return

        payload = event.get("payload")
        if isinstance(payload, dict):
            action = str(payload.get("action", "")).lower()
            if action == "restart_daemon":
                return

        peer = str(event.get("source_peer", "local")) or "local"
        event_time = self._parse_time(event.get("timestamp"))
        key = (peer, source)
        history = self._events[key]
        history.append(event_time)
        cutoff = event_time - self._window
        while history and history[0] < cutoff:
            history.popleft()

        if len(history) < self._threshold:
            return

        last_request = self._last_request.get(key)
        if last_request and event_time - last_request < self._cooldown:
            return

        reason = self._build_reason(event)
        scope = "federated" if peer not in {"", "local"} else "local"
        target_peer = peer if scope == "federated" else None
        self._publish_restart_request(source, reason, scope=scope, target_peer=target_peer)
        self._last_request[key] = event_time

    def _parse_time(self, value: object) -> datetime:
        if isinstance(value, str) and value:
            text = value
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError:
                pass
            else:
                if parsed.tzinfo is None:
                    return parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
        return datetime.now(timezone.utc)

    def _build_reason(self, event: dict[str, object]) -> str:
        event_type = str(event.get("event_type", "unknown"))
        payload = event.get("payload")
        detail: str | None = None
        if isinstance(payload, dict):
            detail_value = payload.get("detail") or payload.get("reason")
            if detail_value:
                detail = str(detail_value)
        base = f"codex_detected_repeated_failures:{event_type}"
        return f"{base}:{detail}" if detail else base

    def _publish_restart_request(
        self,
        daemon_name: str,
        reason: str,
        *,
        scope: str,
        target_peer: str | None = None,
    ) -> None:
        payload = {
            "action": "restart_daemon",
            "daemon": daemon_name,
            "daemon_name": daemon_name,
            "reason": reason,
            "scope": scope,
        }
        if target_peer and target_peer not in {"", "local"}:
            payload["target_peer"] = target_peer
        pulse_bus.publish(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_daemon": "codex",
                "event_type": "restart_request",
                "priority": "critical",
                "payload": payload,
            }
        )


CRITICAL_FAILURE_MONITOR = _CriticalFailureMonitor()


def reset_failure_monitor() -> None:
    CRITICAL_FAILURE_MONITOR.reset()


def _load_last_session_timestamp() -> datetime | None:
    try:
        data = json.loads(CODEX_SESSION_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None
    ts = data.get("ts")
    if not isinstance(ts, str):
        return None
    try:
        parsed = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)


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


INTEGRITY_LOG = Path("/daemon/logs/integrity.jsonl")


def run_integrity_check() -> bool:
    """Record a basic integrity check result."""
    INTEGRITY_LOG.parent.mkdir(parents=True, exist_ok=True)
    passed = True
    with open(INTEGRITY_LOG, "a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "event": "integrity_check",
                    "passed": passed,
                }
            )
            + "\n"
        )
    return passed


def run_ci(ledger_queue: Queue) -> bool:
    """Run full diagnostics and integrity check, logging the outcome."""
    passed, summary, _ = run_diagnostics()
    integrity = run_integrity_check()
    ci_passed = passed and integrity
    ledger_queue.put(
        {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": "ci_passed" if ci_passed else "ci_failed",
            "summary": summary if not ci_passed else "",
            "codex_mode": CODEX_MODE,
            "ci_passed": ci_passed,
        }
    )
    return ci_passed


def self_repair_check(ledger_queue: Queue | None = None) -> dict | None:
    """Trigger an immediate Codex self-repair cycle."""

    queue = ledger_queue if ledger_queue is not None else Queue()
    with _SELF_REPAIR_LOCK:
        return run_once(queue)


def parse_diff_files(diff: str) -> list[str]:
    files: list[str] = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            files.append(line[6:])
    return files


def parse_failing_tests(output: str) -> list[str]:
    """Extract failing test identifiers from pytest output."""
    return re.findall(r"FAILED (\S+)", output)


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


def send_notifications(entry: dict) -> None:
    """Send repair summaries to configured targets."""
    if not CODEX_NOTIFY or entry.get("verified") is not True:
        return
    summary = {
        "ts": entry.get("ts"),
        "files_changed": entry.get("files_changed", []),
        "iterations": entry.get("iterations", 0),
        "ci_passed": entry.get("ci_passed", False),
    }
    data = json.dumps(summary).encode("utf-8")
    for target in CODEX_NOTIFY:
        if target == "stdout":
            print(json.dumps(summary))
        else:
            try:  # pragma: no cover - best effort
                req = urllib.request.Request(
                    target, data=data, headers={"Content-Type": "application/json"}
                )
                urllib.request.urlopen(req, timeout=5)
            except Exception:
                continue


def load_ethics() -> str:
    """Combine NEWLEGACY and current vows for Codex prompts."""
    legacy = ""
    try:
        legacy = Path("NEWLEGACY.txt").read_text(encoding="utf-8")
    except Exception:
        pass
    vows = ""
    vow_dir = Path("/vow")
    if vow_dir.exists():
        for vf in sorted(vow_dir.glob("*")):
            try:
                vows += vf.read_text(encoding="utf-8") + "\n"
            except Exception:
                continue
    return f"{legacy}\n{vows}".strip()


def requires_confirm(files: list[str]) -> bool:
    """Return True if any path is privileged."""
    return any(any(p in f for p in PRIVILEGED_PATTERNS) for f in files)


def confirm_patch() -> bool:
    resp = input("Patch touches privileged files. Apply? [y/N]: ").strip().lower()
    return resp in {"y", "yes"}


def process_request(task_file: Path, ledger_queue: Queue) -> dict:
    """Handle a single expansion request file."""
    spec = json.loads(task_file.read_text(encoding="utf-8"))
    task_file.unlink()
    task = spec.get("task", "")
    prefix = load_ethics()
    prompt = (
        f"{prefix}\n{task}\n"
        "Respond with a JSON object mapping file paths to file contents."
    )
    proc = subprocess.run(["codex", "exec", prompt], capture_output=True, text=True)
    response = proc.stdout.strip()
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    CODEX_PATCH_DIR.mkdir(parents=True, exist_ok=True)
    patch_path = CODEX_PATCH_DIR / f"expand_{timestamp}.json"
    patch_path.write_text(response, encoding="utf-8")
    CODEX_REASONING_DIR.mkdir(parents=True, exist_ok=True)
    trace_path = CODEX_REASONING_DIR / f"trace_{timestamp}.json"
    trace_path.write_text(
        json.dumps(
            {
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "prompt": prompt,
                "response": response,
            }
        ),
        encoding="utf-8",
    )
    try:
        files_dict = json.loads(response) if response else {}
    except json.JSONDecodeError:
        files_dict = {}
    files_created = list(files_dict.keys())
    confirmed = not requires_confirm(files_created)
    verified = False
    if confirmed and files_dict:
        for fp, content in files_dict.items():
            path = Path(fp)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        verified = run_ci(ledger_queue)
        if verified:
            subprocess.run(["git", "add", *files_created], check=False)
            subprocess.run(
                [
                    "git",
                    "commit",
                    "-m",
                    f"[codex:self_expand] {task}",
                ],
                check=False,
            )
    entry = {
        "event": "self_expand",
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "task": task,
        "files_created": files_created,
        "verified": verified,
        "confirmed": confirmed,
        "reasoning_trace": trace_path.as_posix().lstrip("/"),
    }
    log_activity(
        {
            "ts": entry["ts"],
            "prompt": prompt,
            "files_changed": files_created,
            "verified": verified,
            "codex_patch": patch_path.as_posix().lstrip("/"),
            "iterations": 1,
            "target": "expand",
            "outcome": "success" if verified else "fail",
        }
    )
    ledger_queue.put({**entry, "codex_mode": CODEX_MODE})
    return entry


def run_once(ledger_queue: Queue) -> dict | None:
    """Execute a single Codex self-repair cycle."""

    passed, summary, _ = run_diagnostics()
    if passed:
        return None

    if CODEX_MODE == "observe":
        entry = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "prompt": "",
            "files_changed": [],
            "verified": False,
            "codex_patch": "",
            "iterations": 0,
            "target": CODEX_FOCUS,
            "outcome": "observed",
            "summary": summary,
        }
        log_activity(entry)
        ledger_entry = {
            **entry,
            "event": "codex_observe",
            "codex_mode": CODEX_MODE,
            "ci_passed": False,
        }
        ledger_queue.put(ledger_entry)
        return ledger_entry

    failing_tests = parse_failing_tests(summary)
    prompt = (
        "Fix the following issues in SentientOS based on pytest output:\n"
        f"{summary}\n"
        "Output a unified diff."
    )
    proc = subprocess.run(["codex", "exec", prompt], capture_output=True, text=True)
    diff_output = proc.stdout

    CODEX_SUGGEST_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    patch_path = CODEX_SUGGEST_DIR / f"patch_{timestamp}.diff"
    patch_path.write_text(diff_output, encoding="utf-8")

    CODEX_REASONING_DIR.mkdir(parents=True, exist_ok=True)
    trace_path = CODEX_REASONING_DIR / f"trace_{timestamp}.json"
    trace_path.write_text(
        json.dumps(
            {
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "prompt": prompt,
                "response": diff_output,
                "tests_failed": failing_tests,
            }
        ),
        encoding="utf-8",
    )

    files_changed = parse_diff_files(diff_output)
    confirmed = is_safe(files_changed)

    suggestion_entry = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "event": "self_repair_suggested",
        "tests_failed": failing_tests,
        "patch_file": patch_path.as_posix().lstrip("/"),
        "codex_patch": patch_path.as_posix().lstrip("/"),
        "files_changed": files_changed,
        "confirmed": confirmed,
        "codex_mode": CODEX_MODE,
        "iterations": 1,
        "outcome": "suggested" if confirmed else "halted",
        "target": CODEX_FOCUS,
        "verified": False,
    }
    log_activity({**suggestion_entry, "prompt": prompt})
    ledger_queue.put(suggestion_entry)

    if not confirmed or not files_changed:
        return suggestion_entry

    if not apply_patch(diff_output):
        fail_entry = {
            **suggestion_entry,
            "event": "self_repair_failed",
            "reason": "patch_apply_failed",
            "outcome": "fail",
        }
        log_activity(fail_entry)
        ledger_queue.put(fail_entry)
        return fail_entry

    tests_passed, new_summary, _ = run_diagnostics()
    if tests_passed:
        subprocess.run(["git", "add", "-A"], check=False)
        subprocess.run(
            ["git", "commit", "-m", "[codex:self_repair] auto-patch applied"],
            check=False,
        )
        success_entry = {
            **suggestion_entry,
            "event": "self_repair",
            "verified": True,
            "outcome": "success",
            "ci_passed": True,
        }
        log_activity(success_entry)
        ledger_queue.put(success_entry)
        send_notifications(success_entry)
        return success_entry

    fail_entry = {
        **suggestion_entry,
        "event": "self_repair_failed",
        "reason": new_summary,
        "outcome": "fail",
    }
    log_activity(fail_entry)
    ledger_queue.put(fail_entry)
    return fail_entry


def run_loop(stop: threading.Event, ledger_queue: Queue) -> None:
    if CODEX_MODE in {"full", "expand"}:
        threading.Thread(
            target=cpu_ram_daemon, args=(stop, ledger_queue, CONFIG), daemon=True
        ).start()

    pulse_subscription: pulse_bus.PulseSubscription | None = None

    def _pulse_handler(event: dict) -> None:
        CRITICAL_FAILURE_MONITOR.record(event)
        if str(event.get("priority", "info")).lower() != "critical":
            return
        if event.get("event_type") in CRITICAL_PULSE_EVENTS:
            self_repair_check(ledger_queue)

    codex_runs = 0
    total_iterations = 0
    passes = 0
    failures = 0

    last_run = _load_last_session_timestamp()
    if pulse_federation.is_enabled():
        try:
            pulse_federation.request_recent_events(FEDERATION_REPLAY_MINUTES)
        except Exception:  # pragma: no cover - federation failures best-effort
            logger.warning("Unable to replay federated pulse history", exc_info=True)
    if last_run is not None:
        for event in pulse_bus.replay(last_run):
            CRITICAL_FAILURE_MONITOR.record(event)
            if str(event.get("priority", "info")).lower() != "critical":
                continue
            if event.get("event_type") in CRITICAL_PULSE_EVENTS:
                self_repair_check(ledger_queue)

    def write_session() -> None:
        CODEX_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        session = {
            "runs": codex_runs,
            "iterations": total_iterations,
            "passes": passes,
            "failures": failures,
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        CODEX_SESSION_FILE.write_text(json.dumps(session), encoding="utf-8")

    try:
        pulse_subscription = pulse_bus.subscribe(_pulse_handler, priorities=["critical"])
        write_session()
        while not stop.is_set():
            try:
                result = None
                if CODEX_MODE == "expand":
                    CODEX_REQUEST_DIR.mkdir(parents=True, exist_ok=True)
                    requests = sorted(CODEX_REQUEST_DIR.glob("*"))
                    if requests:
                        result = process_request(requests[0], ledger_queue)
                        codex_runs += 1
                        total_iterations += 1
                        if result.get("verified"):
                            passes += 1
                        else:
                            failures += 1
                        write_session()
                else:
                    result = run_once(ledger_queue)
                    if result:
                        codex_runs += 1
                        total_iterations += result.get("iterations", 0)
                        if result["outcome"] == "success":
                            passes += 1
                        elif result["outcome"] == "fail":
                            failures += 1
                        write_session()
            except Exception as exc:  # pragma: no cover - best effort logging
                log_activity(
                    {
                        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "error": str(exc),
                        "files_changed": [],
                        "verified": False,
                        "codex_patch": "",
                        "iterations": 0,
                        "target": CODEX_FOCUS,
                        "outcome": "fail",
                    }
                )
                failures += 1
            if stop.wait(CODEX_INTERVAL):
                break

        write_session()
        ledger_queue.put(
            {
                "event": "codex_session_report",
                "codex_mode": CODEX_MODE,
                "runs": codex_runs,
                "iterations": total_iterations,
                "passes": passes,
                "failures": failures,
            }
        )
        ledger_queue.put(
            {
                "event": "codex_dashboard_report",
                "codex_mode": CODEX_MODE,
                "runs": codex_runs,
                "iterations": total_iterations,
                "passes": passes,
                "failures": failures,
                "dashboard": True,
            }
        )
    finally:
        if pulse_subscription is not None:
            pulse_subscription.unsubscribe()
