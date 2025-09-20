from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import json
import logging
import os
import re
import subprocess
import threading
import time
import urllib.request
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from queue import Queue
from typing import Iterable, Mapping, Tuple

import yaml
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import DiffLexer

from sentientos.daemons import pulse_bus, pulse_federation

from daemon.cpu_ram_daemon import run_loop as cpu_ram_daemon
CODEX_LOG = Path("/daemon/logs/codex.jsonl")
# Directory for storing Codex suggestion patches
CODEX_SUGGEST_DIR = Path("/glow/codex_suggestions/")
CODEX_PATCH_DIR = CODEX_SUGGEST_DIR  # backward compatibility
CODEX_SESSION_FILE = Path("/daemon/logs/codex_session.json")
CODEX_REQUEST_DIR = Path("/glow/codex_requests/")
CODEX_REASONING_DIR = Path("/daemon/logs/codex_reasoning/")
MONITORING_METRICS_PATH = Path(
    os.getenv(
        "MONITORING_METRICS_PATH",
        str(Path(os.getenv("MONITORING_GLOW_ROOT", "/glow/monitoring")) / "metrics.jsonl"),
    )
)

PRIVILEGED_PATTERNS = ["/vow/", "NEWLEGACY.txt", "init.py", "privilege.py"]
OFF_LIMIT_PATTERNS = ["/vow/", "NEWLEGACY.txt"]
_VEIL_METADATA_SUFFIX = ".veil.json"
_PATCH_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")

PREDICTIVE_SAFETY_CONTEXT = (
    "Safety Context: Maintain SentientOS safeguards. Do not modify /vow, NEWLEGACY, "
    "or other privileged files. Focus on adaptive, well-tested improvements that respect "
    "monitoring transparency."
)

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
    # Federation predictive handling
    "federated_auto_apply": False,
    "federation_peer_name": "",
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

LOCAL_PEER_NAME = (
    str(
        CONFIG.get("federation_peer_name")
        or os.getenv("FEDERATION_PEER_NAME", "local")
    ).strip()
    or "local"
)
FEDERATED_AUTO_APPLY = bool(CONFIG.get("federated_auto_apply", False))


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


def _to_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _format_window(seconds: int) -> str:
    if seconds <= 0:
        return "unknown"
    if seconds % 3600 == 0:
        hours = seconds // 3600
        return f"{hours}h"
    if seconds % 60 == 0:
        minutes = seconds // 60
        return f"{minutes}m"
    return f"{seconds}s"


def _load_metrics_snapshots(limit: int = 25) -> list[dict[str, object]]:
    path = MONITORING_METRICS_PATH
    try:
        with path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except FileNotFoundError:
        logger.debug("Monitoring metrics file missing at %s", path)
        return []
    snapshots: list[dict[str, object]] = []
    for entry in lines[-limit:]:
        text = entry.strip()
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.debug("Skipping malformed metrics entry")
            continue
        if isinstance(data, dict):
            snapshots.append(data)
    return snapshots


class _PredictiveRepairManager:
    def __init__(self) -> None:
        self._latest_summary: dict[str, object] | None = None

    def record_summary(self, event: dict[str, object]) -> None:
        payload = event.get("payload")
        if isinstance(payload, dict):
            self._latest_summary = {
                "timestamp": str(event.get("timestamp", "")),
                "payload": dict(payload),
            }

    def handle_alert(self, event: dict[str, object], ledger_queue: Queue) -> None:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            return
        anomaly = dict(payload)
        anomaly.setdefault("timestamp", str(event.get("timestamp", "")))
        source_daemon = str(anomaly.get("source_daemon", "")).strip()
        if not source_daemon:
            return
        target_peer = str(event.get("source_peer", "local")) or "local"
        if not self._should_trigger(anomaly):
            return
        analysis = self._analyze_history(source_daemon, anomaly)
        if target_peer not in {"", "local"}:
            logger.info(
                "Codex predictive analysis triggered for %s on peer %s",
                source_daemon,
                target_peer,
            )
        else:
            logger.info("Codex predictive analysis triggered for %s", source_daemon)
        self._suggest_patch(
            source_daemon,
            anomaly,
            analysis,
            ledger_queue,
            target_peer=None if target_peer in {"", "local"} else target_peer,
        )

    def _should_trigger(self, anomaly: Mapping[str, object]) -> bool:
        observed = _to_int(anomaly.get("observed"))
        threshold = _to_int(anomaly.get("threshold"))
        if observed <= 0 or threshold <= 0:
            return False
        if observed < threshold:
            return False
        if max(observed, threshold) < 5:
            return False
        return True

    def _analyze_history(
        self, daemon_name: str, anomaly: Mapping[str, object]
    ) -> dict[str, object] | None:
        snapshots = _load_metrics_snapshots()
        if not snapshots:
            return None

        total_windows = 0
        elevated_windows = 0
        preferred_window: str | None = None
        anomaly_snapshots = 0
        event_type = str(anomaly.get("event_type", ""))

        for snapshot in snapshots:
            windows = snapshot.get("windows")
            if not isinstance(windows, Mapping):
                continue
            for label, metrics in windows.items():
                metrics_map = metrics if isinstance(metrics, Mapping) else {}
                per_daemon = metrics_map.get("per_daemon")
                if not isinstance(per_daemon, Mapping):
                    continue
                data = per_daemon.get(daemon_name)
                if not isinstance(data, Mapping):
                    continue
                total = _to_int(data.get("total"))
                priority_counts = data.get("priority")
                warnings = 0
                if isinstance(priority_counts, Mapping):
                    warnings = _to_int(priority_counts.get("warning")) + _to_int(
                        priority_counts.get("critical")
                    )
                if total <= 0:
                    continue
                total_windows += 1
                ratio = warnings / total if total else 0.0
                if ratio >= 0.5:
                    elevated_windows += 1
                    preferred_window = str(label)

        for snapshot in snapshots:
            anomalies = snapshot.get("anomalies")
            if not isinstance(anomalies, Iterable):
                continue
            for candidate in anomalies:
                if not isinstance(candidate, Mapping):
                    continue
                if str(candidate.get("source_daemon", "")) != daemon_name:
                    continue
                candidate_type = str(candidate.get("event_type", ""))
                if event_type and candidate_type and candidate_type != event_type:
                    continue
                anomaly_snapshots += 1
                break

        if total_windows == 0 and anomaly_snapshots == 0:
            return None

        percentage = (elevated_windows / total_windows * 100) if total_windows else 0.0
        parts: list[str] = []
        if total_windows:
            parts.append(
                f"{percentage:.1f}% of monitoring windows ({elevated_windows}/{total_windows}) "
                f"show warning or critical trends for {daemon_name}."
            )
        if anomaly_snapshots:
            parts.append(
                f"{anomaly_snapshots} verified snapshots recorded matching anomalies."
            )
        summary = " ".join(parts) if parts else f"No recent metrics for {daemon_name}."
        return {
            "summary": summary,
            "percentage": percentage,
            "total_windows": total_windows,
            "elevated_windows": elevated_windows,
            "anomaly_snapshots": anomaly_snapshots,
            "preferred_window": preferred_window,
        }

    def _suggest_patch(
        self,
        daemon_name: str,
        anomaly: Mapping[str, object],
        analysis: dict[str, object] | None,
        ledger_queue: Queue,
        *,
        target_peer: str | None = None,
    ) -> None:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        analysis_window = _format_window(_to_int(anomaly.get("window_seconds")))
        summary_text = (
            str(analysis.get("summary")) if analysis is not None else f"No historical metrics for {daemon_name}."
        )
        safety_sections = []
        ethics = load_ethics()
        if ethics:
            safety_sections.append(ethics)
        safety_sections.append(PREDICTIVE_SAFETY_CONTEXT)
        safety_text = "\n".join(safety_sections)
        prompt = (
            f"{safety_text}\n"
            "You are assisting CodexDaemon with predictive self-repair.\n"
            f"Focus on resilient mitigations for {daemon_name}.\n"
            f"Anomaly details: {json.dumps(anomaly, sort_keys=True)}\n"
            f"Historical pattern: {summary_text}\n"
            "Suggest code changes that add adaptive thresholds, backoff logic, or richer logging while "
            "respecting safety policies. Respond with a unified diff."
        )
        proc = subprocess.run(["codex", "exec", prompt], capture_output=True, text=True)
        diff_output = proc.stdout

        CODEX_SUGGEST_DIR.mkdir(parents=True, exist_ok=True)
        if target_peer:
            sanitized_peer = re.sub(r"[^a-zA-Z0-9_.-]", "_", target_peer)
            patch_path = CODEX_SUGGEST_DIR / f"predictive_{sanitized_peer}_{timestamp}.diff"
        else:
            patch_path = CODEX_SUGGEST_DIR / f"predictive_{timestamp}.diff"
        files_changed = parse_diff_files(diff_output)
        off_limits = bool(files_changed and touches_off_limits(files_changed))
        needs_confirmation = bool(files_changed and requires_veil(files_changed))
        if off_limits:
            patch_path.write_text(
                "# Predictive patch rejected: attempted to modify privileged files.\n",
                encoding="utf-8",
            )
            files_changed = []
            diff_to_apply = ""
        else:
            patch_path.write_text(diff_output, encoding="utf-8")
            diff_to_apply = diff_output

        suggestion_ts = time.strftime("%Y-%m-%d %H:%M:%S")
        patch_ref = patch_path.as_posix().lstrip("/")

        log_activity(
            {
                "ts": suggestion_ts,
                "prompt": prompt,
                "files_changed": files_changed,
                "verified": False,
                "codex_patch": patch_ref,
                "iterations": 1,
                "target": "predictive",
                "outcome": "suggested" if diff_to_apply else "blocked",
                "analysis_window": analysis_window,
                "triggering_anomaly": anomaly,
                "pattern_summary": summary_text,
                "target_peer": target_peer or "local",
                "requires_confirmation": needs_confirmation,
            }
        )

        ledger_queue.put(
            {
                "ts": suggestion_ts,
                "event": "self_predict_suggested",
                "codex_mode": CODEX_MODE,
                "triggering_anomaly": anomaly,
                "analysis_window": analysis_window,
                "patch_file": patch_ref,
                "status": "suggested",
                "files_changed": files_changed,
                "pattern_summary": summary_text,
                "target_peer": target_peer or "local",
                "requires_confirmation": needs_confirmation,
            }
        )

        if target_peer and diff_to_apply:
            _publish_predictive_event(
                status="suggested",
                source_peer=LOCAL_PEER_NAME,
                target_peer=target_peer,
                target_daemon=daemon_name,
                anomaly_pattern=summary_text,
                patch_path=patch_ref,
                patch_diff=diff_to_apply,
                anomaly=anomaly,
                files_changed=files_changed,
                analysis_window=analysis_window,
            )
            _log_federated_event(
                ledger_queue,
                timestamp=suggestion_ts,
                status="suggested",
                source_peer=LOCAL_PEER_NAME,
                target_daemon=daemon_name,
                anomaly=anomaly,
                anomaly_pattern=summary_text,
                patch_path=patch_ref,
                target_peer=target_peer,
            )

        if (
            diff_to_apply
            and not target_peer
            and CODEX_MODE == "expand"
            and files_changed
            and is_safe(files_changed)
            and not needs_confirmation
        ):
            applied = apply_patch(diff_to_apply)
            verified = False
            if applied:
                verified = run_ci(ledger_queue)
                ledger_queue.put(
                    {
                        "ts": suggestion_ts,
                        "event": "self_predict_applied",
                        "codex_mode": CODEX_MODE,
                        "triggering_anomaly": anomaly,
                        "analysis_window": analysis_window,
                        "patch_file": patch_ref,
                        "status": "applied",
                        "verification_result": bool(verified),
                        "files_changed": files_changed,
                    }
                )
                log_activity(
                    {
                        "ts": suggestion_ts,
                        "prompt": prompt,
                        "files_changed": files_changed,
                        "verified": bool(verified),
                        "codex_patch": patch_ref,
                        "iterations": 1,
                        "target": "predictive",
                        "outcome": "success" if verified else "fail",
                        "analysis_window": analysis_window,
                        "triggering_anomaly": anomaly,
                        "pattern_summary": summary_text,
                    }
                )

        if (
            diff_to_apply
            and not target_peer
            and CODEX_MODE == "expand"
            and files_changed
            and needs_confirmation
        ):
            _register_veil_request(
                ledger_queue,
                patch_path=patch_path,
                patch_ref=patch_ref,
                scope="local",
                anomaly_pattern=summary_text,
                files_changed=files_changed,
                requires_confirmation=True,
                target_peer=None,
                source_peer=LOCAL_PEER_NAME,
            )

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


def _veil_metadata_path(patch_path: Path) -> Path:
    base = patch_path.with_suffix("")
    return base.with_suffix(_VEIL_METADATA_SUFFIX)


def _register_veil_request(
    ledger_queue: Queue,
    *,
    patch_path: Path,
    patch_ref: str,
    scope: str,
    anomaly_pattern: str,
    files_changed: list[str],
    requires_confirmation: bool,
    target_peer: str | None,
    source_peer: str | None,
) -> dict[str, object]:
    """Persist veil metadata, log the ledger entry, and publish the pulse."""

    patch_id = Path(patch_ref).stem or patch_path.stem
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    metadata = {
        "patch_id": patch_id,
        "patch_path": patch_ref,
        "scope": scope,
        "anomaly_pattern": anomaly_pattern,
        "requires_confirmation": bool(requires_confirmation),
        "status": "pending",
        "files_changed": list(files_changed),
        "source_peer": (source_peer or ""),
        "target_peer": (target_peer or ""),
        "timestamp": timestamp,
        "codex_mode": CODEX_MODE,
    }
    metadata_path = _veil_metadata_path(patch_path)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")

    ledger_entry: dict[str, object] = {
        "ts": timestamp,
        "event": "veil_pending",
        "codex_mode": CODEX_MODE,
        "patch_file": patch_ref,
        "patch_id": patch_id,
        "scope": scope,
        "requires_confirmation": bool(requires_confirmation),
        "files_changed": list(files_changed),
        "anomaly_pattern": anomaly_pattern,
        "source_peer": source_peer or "",
        "target_peer": target_peer or "",
    }
    ledger_queue.put(ledger_entry)

    log_activity({**metadata, "event": "veil_pending", "ts": timestamp})

    payload: dict[str, object] = {
        "patch_id": patch_id,
        "patch_path": patch_ref,
        "scope": scope,
        "anomaly_pattern": anomaly_pattern,
        "requires_confirmation": bool(requires_confirmation),
        "files_changed": list(files_changed),
        "source_peer": source_peer or "",
        "target_peer": target_peer or "",
    }
    pulse_bus.publish(
        {
            "timestamp": datetime.utcnow().isoformat(),
            "source_daemon": "CodexDaemon",
            "event_type": "veil_request",
            "priority": "warning",
            "payload": payload,
        }
    )
    return metadata


def _normalize_patch_id(patch_id: str) -> str:
    text = str(patch_id).strip()
    if not text:
        raise ValueError("patch_id is required")
    if "/" in text or "\\" in text or ".." in text:
        raise ValueError("patch_id contains invalid path separators")
    if not _PATCH_ID_PATTERN.fullmatch(text):
        raise ValueError("patch_id contains unsupported characters")
    return text


def _load_veil_record(patch_id: str) -> tuple[Path, dict[str, object]]:
    normalized = _normalize_patch_id(patch_id)
    metadata_path = CODEX_SUGGEST_DIR / f"{normalized}{_VEIL_METADATA_SUFFIX}"
    if not metadata_path.exists():
        raise FileNotFoundError(f"No veil metadata found for patch {normalized}")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Veil metadata for {normalized} is corrupted") from exc
    if not isinstance(metadata, dict):
        raise ValueError("Veil metadata must be a JSON object")
    return metadata_path, metadata


def _resolve_patch_path(patch_ref: str) -> Path:
    text = str(patch_ref).strip()
    if not text:
        raise ValueError("veil metadata missing patch_path")
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = Path("/") / text
    resolved = candidate.resolve(strict=False)
    suggest_root = CODEX_SUGGEST_DIR.resolve(strict=False)
    if resolved == suggest_root or suggest_root in resolved.parents:
        return resolved
    raise PermissionError("Veil patch path escapes the suggestion directory")


def load_veil_metadata(patch_id: str) -> dict[str, object]:
    """Return stored metadata for a veil-protected patch."""

    _, metadata = _load_veil_record(patch_id)
    return metadata


def _publish_veil_resolution(
    event_type: str, metadata: Mapping[str, object], extra: Mapping[str, object]
) -> None:
    payload: dict[str, object] = {
        "patch_id": metadata.get("patch_id", ""),
        "patch_path": metadata.get("patch_path", ""),
        "scope": metadata.get("scope", ""),
        "anomaly_pattern": metadata.get("anomaly_pattern", ""),
        "requires_confirmation": metadata.get("requires_confirmation", True),
        "source_peer": metadata.get("source_peer", ""),
        "target_peer": metadata.get("target_peer", ""),
    }
    for key, value in extra.items():
        payload[key] = value
    priority = "info" if event_type == "veil_confirmed" else "warning"
    pulse_bus.publish(
        {
            "timestamp": datetime.utcnow().isoformat(),
            "source_daemon": "CodexDaemon",
            "event_type": event_type,
            "priority": priority,
            "payload": payload,
        }
    )


def confirm_veil_patch(patch_id: str) -> dict[str, object]:
    """Apply a veil-protected patch and log the confirmation."""

    metadata_path, metadata = _load_veil_record(patch_id)
    status = str(metadata.get("status", "pending")).lower()
    if status != "pending":
        raise ValueError(f"Patch {patch_id} is not pending confirmation")

    files_changed_raw = metadata.get("files_changed", [])
    files_changed = [str(path) for path in files_changed_raw if isinstance(path, str)]
    if touches_off_limits(files_changed):
        raise PermissionError("Off-limit patches cannot be confirmed")

    patch_ref = str(metadata.get("patch_path", "")).strip()
    patch_file = _resolve_patch_path(patch_ref)
    if not patch_file.exists():
        raise FileNotFoundError(f"Patch file missing for {patch_id}")

    diff = patch_file.read_text(encoding="utf-8")
    applied = apply_patch(diff)
    ci_passed = False
    if applied:
        ci_passed = bool(run_ci(Queue()))

    resolved_ts = time.strftime("%Y-%m-%d %H:%M:%S")
    metadata.update(
        {
            "status": "confirmed" if applied else "failed",
            "resolved_at": resolved_ts,
            "applied": bool(applied),
            "ci_passed": bool(ci_passed),
        }
    )
    metadata_path.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")

    log_activity(
        {
            "ts": resolved_ts,
            "event": "veil_confirmed",
            "patch_id": metadata.get("patch_id", patch_id),
            "patch_file": patch_ref,
            "scope": metadata.get("scope", ""),
            "applied": bool(applied),
            "ci_passed": bool(ci_passed),
            "source_peer": metadata.get("source_peer", ""),
            "target_peer": metadata.get("target_peer", ""),
            "anomaly_pattern": metadata.get("anomaly_pattern", ""),
        }
    )

    extra_payload = {"applied": bool(applied), "ci_passed": bool(ci_passed)}
    if not applied:
        extra_payload["error"] = "apply_failed"
    _publish_veil_resolution("veil_confirmed", metadata, extra_payload)

    result = {
        "patch_id": metadata.get("patch_id", patch_id),
        "applied": bool(applied),
        "ci_passed": bool(ci_passed),
    }
    if not applied:
        result["error"] = "apply_failed"
    return result


def reject_veil_patch(patch_id: str) -> dict[str, object]:
    """Reject a veil-protected patch and record the decision."""

    metadata_path, metadata = _load_veil_record(patch_id)
    status = str(metadata.get("status", "pending")).lower()
    if status != "pending":
        raise ValueError(f"Patch {patch_id} is not pending confirmation")

    patch_ref = str(metadata.get("patch_path", "")).strip()
    patch_file = _resolve_patch_path(patch_ref)
    if patch_file.exists():
        try:
            patch_file.unlink()
        except OSError:
            pass

    resolved_ts = time.strftime("%Y-%m-%d %H:%M:%S")
    metadata.update({"status": "rejected", "resolved_at": resolved_ts})
    metadata_path.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")

    log_activity(
        {
            "ts": resolved_ts,
            "event": "veil_rejected",
            "patch_id": metadata.get("patch_id", patch_id),
            "patch_file": patch_ref,
            "scope": metadata.get("scope", ""),
            "source_peer": metadata.get("source_peer", ""),
            "target_peer": metadata.get("target_peer", ""),
            "anomaly_pattern": metadata.get("anomaly_pattern", ""),
        }
    )

    _publish_veil_resolution("veil_rejected", metadata, {"decision": "rejected"})

    return {"patch_id": metadata.get("patch_id", patch_id), "status": "rejected"}


_PEER_PATCH_SANITIZE = re.compile(r"[^0-9]")


def _peer_patch_filename(timestamp: str) -> str:
    cleaned = _PEER_PATCH_SANITIZE.sub("", timestamp or "")
    if not cleaned:
        cleaned = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"peer_{cleaned}.diff"


def _log_federated_event(
    ledger_queue: Queue,
    *,
    timestamp: str,
    status: str,
    source_peer: str,
    target_daemon: str,
    anomaly: Mapping[str, object] | object | None,
    anomaly_pattern: str,
    patch_path: str,
    target_peer: str | None = None,
    verification_result: bool | None = None,
    note: str | None = None,
    requires_confirmation: bool | None = None,
) -> None:
    entry: dict[str, object] = {
        "ts": timestamp,
        "event": "federated_predictive_event",
        "status": status,
        "source_peer": source_peer,
        "target_peer": target_peer or "",
        "target_daemon": target_daemon,
        "anomaly_pattern": anomaly_pattern,
        "triggering_anomaly": anomaly,
        "patch_path": patch_path,
    }
    if verification_result is not None:
        entry["verification_result"] = bool(verification_result)
    if note:
        entry["note"] = note
    if requires_confirmation is not None:
        entry["requires_confirmation"] = bool(requires_confirmation)
    ledger_queue.put(entry)


def _publish_predictive_event(
    *,
    status: str,
    source_peer: str,
    target_peer: str,
    target_daemon: str,
    anomaly_pattern: str,
    patch_path: str,
    patch_diff: str | None,
    anomaly: Mapping[str, object] | object | None,
    files_changed: list[str] | None,
    analysis_window: str,
) -> None:
    payload: dict[str, object] = {
        "source_peer": source_peer,
        "target_peer": target_peer,
        "target_daemon": target_daemon,
        "anomaly_pattern": anomaly_pattern,
        "patch_path": patch_path,
        "status": status,
        "analysis_window": analysis_window,
        "triggering_anomaly": anomaly,
    }
    if patch_diff:
        payload["patch_diff"] = patch_diff
    if files_changed:
        payload["files_changed"] = files_changed
    pulse_bus.publish(
        {
            "timestamp": datetime.utcnow().isoformat(),
            "source_daemon": "CodexDaemon",
            "event_type": "predictive_suggestion",
            "priority": "info",
            "payload": payload,
        }
    )


def _process_predictive_suggestion(event: Mapping[str, object], ledger_queue: Queue) -> None:
    if str(event.get("event_type", "")) != "predictive_suggestion":
        return
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        return
    origin_peer = str(event.get("source_peer", "local")) or "local"
    if origin_peer in {"", "local"}:
        return
    status = str(payload.get("status", "")).lower()
    if status not in {"suggested", "applied"}:
        return
    target_peer_value = payload.get("target_peer") or payload.get("target_node")
    target_peer = str(target_peer_value).strip() if target_peer_value else ""
    if target_peer and target_peer not in {"local", LOCAL_PEER_NAME}:
        return
    target_daemon = str(payload.get("target_daemon", "")).strip()
    anomaly_pattern = str(payload.get("anomaly_pattern", "")).strip()
    anomaly = payload.get("triggering_anomaly")
    patch_diff = payload.get("patch_diff")
    event_timestamp = str(event.get("timestamp", ""))
    ledger_ts = time.strftime("%Y-%m-%d %H:%M:%S")
    target_label = target_peer or LOCAL_PEER_NAME
    patch_path_hint = str(payload.get("patch_path", "")).strip()

    if status == "applied":
        _log_federated_event(
            ledger_queue,
            timestamp=ledger_ts,
            status="applied",
            source_peer=origin_peer,
            target_daemon=target_daemon,
            anomaly=anomaly,
            anomaly_pattern=anomaly_pattern,
            patch_path=patch_path_hint,
            target_peer=target_label,
        )
        return

    if not isinstance(patch_diff, str) or not patch_diff.strip():
        _log_federated_event(
            ledger_queue,
            timestamp=ledger_ts,
            status="rejected",
            source_peer=origin_peer,
            target_daemon=target_daemon,
            anomaly=anomaly,
            anomaly_pattern=anomaly_pattern,
            patch_path=patch_path_hint,
            target_peer=target_label,
            note="Empty predictive patch payload",
        )
        return

    files_changed = parse_diff_files(patch_diff)
    off_limits = bool(files_changed and touches_off_limits(files_changed))
    needs_confirmation = bool(files_changed and requires_veil(files_changed))
    if off_limits:
        _log_federated_event(
            ledger_queue,
            timestamp=ledger_ts,
            status="rejected",
            source_peer=origin_peer,
            target_daemon=target_daemon,
            anomaly=anomaly,
            anomaly_pattern=anomaly_pattern,
            patch_path="",
            target_peer=target_label,
            note="Predictive patch touched privileged paths",
        )
        return

    CODEX_SUGGEST_DIR.mkdir(parents=True, exist_ok=True)
    patch_file = CODEX_SUGGEST_DIR / _peer_patch_filename(event_timestamp)
    patch_file.write_text(patch_diff, encoding="utf-8")
    patch_ref = patch_file.as_posix().lstrip("/")

    _log_federated_event(
        ledger_queue,
        timestamp=ledger_ts,
        status="suggested",
        source_peer=origin_peer,
        target_daemon=target_daemon,
        anomaly=anomaly,
        anomaly_pattern=anomaly_pattern,
        patch_path=patch_ref,
        target_peer=target_label,
        requires_confirmation=needs_confirmation,
    )

    if not FEDERATED_AUTO_APPLY:
        return

    if not files_changed:
        return

    if needs_confirmation:
        _register_veil_request(
            ledger_queue,
            patch_path=patch_file,
            patch_ref=patch_ref,
            scope="federated",
            anomaly_pattern=anomaly_pattern,
            files_changed=files_changed,
            requires_confirmation=True,
            target_peer=target_label,
            source_peer=origin_peer,
        )
        return

    if not is_safe(files_changed):
        return

    if not apply_patch(patch_diff):
        _log_federated_event(
            ledger_queue,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            status="rejected",
            source_peer=LOCAL_PEER_NAME,
            target_daemon=target_daemon,
            anomaly=anomaly,
            anomaly_pattern=anomaly_pattern,
            patch_path=patch_ref,
            target_peer=target_label,
            note="Failed to apply predictive patch",
        )
        return

    verified = run_ci(ledger_queue)
    apply_ts = time.strftime("%Y-%m-%d %H:%M:%S")
    _log_federated_event(
        ledger_queue,
        timestamp=apply_ts,
        status="applied",
        source_peer=LOCAL_PEER_NAME,
        target_daemon=target_daemon,
        anomaly=anomaly,
        anomaly_pattern=anomaly_pattern,
        patch_path=patch_ref,
        target_peer=target_label,
        verification_result=verified,
    )
    _publish_predictive_event(
        status="applied",
        source_peer=LOCAL_PEER_NAME,
        target_peer=target_label,
        target_daemon=target_daemon,
        anomaly_pattern=anomaly_pattern,
        patch_path=patch_ref,
        patch_diff=patch_diff,
        anomaly=anomaly,
        files_changed=files_changed,
        analysis_window=str(payload.get("analysis_window", "")),
    )

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
    """Return True if any path is privileged or requires confirmation."""
    patterns = set(PRIVILEGED_PATTERNS) | set(CODEX_CONFIRM_PATTERNS)
    return any(any(pattern in f for pattern in patterns) for f in files)


def touches_off_limits(files: list[str]) -> bool:
    """Return True when a patch touches strictly forbidden locations."""
    return any(any(pattern in f for pattern in OFF_LIMIT_PATTERNS) for f in files)


def requires_veil(files: list[str]) -> bool:
    """Return True when confirmation veil is required for these paths."""
    if not files:
        return False
    confirm_patterns = (set(PRIVILEGED_PATTERNS) | set(CODEX_CONFIRM_PATTERNS)) - set(
        OFF_LIMIT_PATTERNS
    )
    if not confirm_patterns:
        return False
    return any(any(pattern in f for pattern in confirm_patterns) for f in files)


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
    monitor_subscription: pulse_bus.PulseSubscription | None = None
    predictive_subscription: pulse_bus.PulseSubscription | None = None
    predictive_manager = _PredictiveRepairManager()

    def _monitor_handler(event: dict) -> None:
        source = str(event.get("source_daemon", ""))
        if source != "MonitoringDaemon":
            return
        event_type = str(event.get("event_type", ""))
        if event_type == "monitor_summary":
            predictive_manager.record_summary(event)
        elif event_type == "monitor_alert":
            predictive_manager.handle_alert(event, ledger_queue)

    def _pulse_handler(event: dict) -> None:
        CRITICAL_FAILURE_MONITOR.record(event)
        priority = str(event.get("priority", "info")).lower()
        event_type = str(event.get("event_type", ""))
        if priority != "critical":
            return
        if event_type in CRITICAL_PULSE_EVENTS:
            self_repair_check(ledger_queue)

    def _predictive_handler(event: dict) -> None:
        _process_predictive_suggestion(event, ledger_queue)

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
            _monitor_handler(event)
            CRITICAL_FAILURE_MONITOR.record(event)
            priority = str(event.get("priority", "info")).lower()
            event_type = str(event.get("event_type", ""))
            if priority != "critical":
                continue
            if event_type in CRITICAL_PULSE_EVENTS:
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
        monitor_subscription = pulse_bus.subscribe(_monitor_handler)
        predictive_subscription = pulse_bus.subscribe(_predictive_handler)
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
        if monitor_subscription is not None:
            monitor_subscription.unsubscribe()
        if pulse_subscription is not None:
            pulse_subscription.unsubscribe()
        if predictive_subscription is not None:
            predictive_subscription.unsubscribe()
