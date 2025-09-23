"""ArchitectDaemon — autonomous Codex meta-orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
import subprocess
from collections import deque
from pathlib import Path
from typing import Callable, Deque, Iterable, Mapping, MutableMapping, Sequence

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from daemon import codex_daemon
from log_utils import append_json
from sentientos.daemons import pulse_bus


ARCHITECT_INTERVAL = float(os.getenv("ARCHITECT_INTERVAL", str(6 * 60 * 60)))
ARCHITECT_MAX_ITERATIONS = int(os.getenv("ARCHITECT_MAX_ITERATIONS", "3"))
ARCHITECT_REQUEST_DIR = Path(
    os.getenv("ARCHITECT_REQUEST_DIR", "/glow/codex_requests")
)
ARCHITECT_SESSION_FILE = Path(
    os.getenv("ARCHITECT_SESSION_FILE", "/daemon/logs/architect_session.json")
)
ARCHITECT_LEDGER_PATH = Path(
    os.getenv("ARCHITECT_LEDGER_PATH", "/daemon/logs/architect_ledger.jsonl")
)

_DEFAULT_CI_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("pytest", "-q"),
    ("verify_audits", "--strict"),
)
_DEFAULT_IMMUTABILITY_COMMAND: tuple[str, ...] = (
    "python",
    "scripts/audit_immutability_verifier.py",
)

SAFETY_ENVELOPE = (
    "Covenant Safety Envelope:\n"
    "- Never modify files under /vow or NEWLEGACY.\n"
    "- Respect privileged paths and immutability manifest entries.\n"
    "- Decline tasks that violate sanctuary ethics or human oversight."
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sanitize_token(text: str) -> str:
    token = text.strip() or "request"
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in token)


def _normalize_mapping(value: Mapping[str, object]) -> dict[str, object]:
    data: dict[str, object] = {}
    for key, val in value.items():
        if isinstance(val, Mapping):
            data[str(key)] = _normalize_mapping(val)
        else:
            data[str(key)] = val
    return data


@dataclass
class ArchitectRequest:
    """Internal representation for an ArchitectDaemon Codex request."""

    architect_id: str
    mode: str
    reason: str
    context: list[dict[str, object]]
    created_at: datetime
    details: dict[str, object] = field(default_factory=dict)
    iterations: int = 0
    max_iterations: int = 1
    status: str = "submitted"
    codex_prefix: str = ""
    prompt_path: Path | None = None
    branch_name: str | None = None
    last_error: str | None = None

    def metadata(self) -> dict[str, object]:
        return {
            "architect_id": self.architect_id,
            "mode": self.mode,
            "reason": self.reason,
            "iterations": self.iterations,
            "max_iterations": self.max_iterations,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "details": dict(self.details),
            "last_error": self.last_error,
        }



class ArchitectDaemon:
    """Meta-orchestrator that coordinates Codex expansion autonomously."""

    def __init__(
        self,
        *,
        request_dir: Path | str | None = None,
        session_file: Path | str | None = None,
        ledger_path: Path | str | None = None,
        interval: float | None = None,
        max_iterations: int | None = None,
        ledger_sink: Callable[[dict[str, object]], None] | None = None,
        pulse_publisher: Callable[[dict[str, object]], Mapping[str, object]] | None = None,
        clock: Callable[[], datetime] | None = None,
        ci_commands: Sequence[Sequence[str]] | None = None,
        immutability_command: Sequence[str] | None = None,
    ) -> None:
        self.request_dir = Path(request_dir) if request_dir else ARCHITECT_REQUEST_DIR
        self.session_file = Path(session_file) if session_file else ARCHITECT_SESSION_FILE
        self.ledger_path = Path(ledger_path) if ledger_path else ARCHITECT_LEDGER_PATH
        self.interval = float(interval if interval is not None else ARCHITECT_INTERVAL)
        self.max_iterations = int(
            max_iterations if max_iterations is not None else ARCHITECT_MAX_ITERATIONS
        )
        self._ledger_sink = ledger_sink
        self._pulse_publisher = pulse_publisher or pulse_bus.publish
        self._clock = clock or _utcnow
        self._ci_commands = [tuple(cmd) for cmd in ci_commands] if ci_commands else [
            tuple(cmd) for cmd in _DEFAULT_CI_COMMANDS
        ]
        self._immutability_command = (
            tuple(immutability_command)
            if immutability_command
            else _DEFAULT_IMMUTABILITY_COMMAND
        )

        self.request_dir.mkdir(parents=True, exist_ok=True)
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)

        self._requests: dict[str, ArchitectRequest] = {}
        self._prefix_index: dict[str, ArchitectRequest] = {}
        self._context_buffer: Deque[dict[str, object]] = deque(maxlen=25)
        self._ledger_buffer: Deque[dict[str, object]] = deque(maxlen=25)
        self._subscription: pulse_bus.PulseSubscription | None = None

        self._session = self._load_session()
        last_reflect = self._session.get("last_reflect")
        self._last_reflect = (
            float(last_reflect)
            if isinstance(last_reflect, (int, float, str)) and str(last_reflect).strip()
            else 0.0
        )

    # ------------------------------------------------------------------
    # Lifecycle hooks
    def start(self) -> None:
        if self._subscription and self._subscription.active:
            return
        self._subscription = pulse_bus.subscribe(self.handle_pulse)

    def stop(self) -> None:
        if self._subscription and self._subscription.active:
            self._subscription.unsubscribe()
        self._subscription = None

    # ------------------------------------------------------------------
    # Session helpers
    def _load_session(self) -> dict[str, object]:
        if not self.session_file.exists():
            return {"runs": 0, "successes": 0, "failures": 0}
        try:
            data = json.loads(self.session_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"runs": 0, "successes": 0, "failures": 0}
        if not isinstance(data, MutableMapping):
            return {"runs": 0, "successes": 0, "failures": 0}
        payload = dict(data)
        payload.setdefault("runs", 0)
        payload.setdefault("successes", 0)
        payload.setdefault("failures", 0)
        return payload

    def _save_session(self) -> None:
        self.session_file.write_text(
            json.dumps(self._session, indent=2, sort_keys=True), encoding="utf-8"
        )

    def _record_success(self) -> None:
        self._session["runs"] = int(self._session.get("runs", 0)) + 1
        self._session["successes"] = int(self._session.get("successes", 0)) + 1
        self._save_session()

    def _record_failure(self) -> None:
        self._session["runs"] = int(self._session.get("runs", 0)) + 1
        self._session["failures"] = int(self._session.get("failures", 0)) + 1
        self._save_session()

    def _now(self) -> datetime:
        return self._clock()

    def _has_active_request(self) -> bool:
        return any(
            req.status in {"submitted", "awaiting_veil"} for req in self._requests.values()
        )

    # ------------------------------------------------------------------
    # Public helpers
    def request_expand(
        self,
        description: str,
        context: Iterable[Mapping[str, object]] | None = None,
    ) -> ArchitectRequest:
        details = {"description": description}
        return self._create_request("expand", description, context, details)

    def request_repair(
        self,
        reason: str,
        context: Iterable[Mapping[str, object]] | None = None,
    ) -> ArchitectRequest:
        details = {"trigger": reason}
        return self._create_request("repair", reason, context, details)

    def request_reflect(
        self,
        topic: str,
        context: Iterable[Mapping[str, object]] | None = None,
    ) -> ArchitectRequest:
        details = {"topic": topic}
        return self._create_request("reflect", topic, context, details)

    def get_request(self, architect_id: str) -> ArchitectRequest | None:
        return self._requests.get(architect_id)

    def tick(self, now: datetime | None = None) -> ArchitectRequest | None:
        timestamp = (now or self._now()).timestamp()
        if self.interval <= 0:
            return None
        if self._has_active_request():
            return None
        if timestamp - self._last_reflect < self.interval:
            return None
        request = self.request_reflect("interval_reflection")
        self._last_reflect = timestamp
        self._session["last_reflect"] = timestamp
        self._save_session()
        return request

    # ------------------------------------------------------------------
    # Event ingestion
    def handle_pulse(self, event: Mapping[str, object]) -> None:
        normalized = self._normalize_pulse_event(event)
        if normalized is None:
            return
        self._context_buffer.append(normalized)
        source = normalized.get("source")
        event_type = normalized.get("event_type")
        if source == "MonitoringDaemon" and event_type == "monitor_alert":
            self.request_repair("monitor_alert")
        elif source == "DriverManager" and event_type == "driver_failure":
            self.request_repair("driver_failure")

    def handle_ledger_entry(self, entry: Mapping[str, object]) -> None:
        normalized = self._normalize_ledger_entry(entry)
        if normalized is None:
            return
        self._ledger_buffer.append(normalized)
        event = normalized.get("event")
        if event == "self_expand":
            request = self._match_request(normalized.get("request_id"))
            if request:
                self._complete_request(request, normalized)
        elif event == "self_expand_rejected":
            request = self._match_request(normalized.get("request_id"))
            if request:
                reason = str(normalized.get("reason", ""))
                self._retry_request(request, reason, normalized)
        elif event == "veil_pending":
            request = self._match_request(normalized.get("patch_id"))
            if request:
                self._surface_veil_request(request, normalized)
        elif event == "self_repair":
            request = self._match_repair_request()
            if request:
                self._complete_request(request, normalized)
        elif event == "self_repair_failed":
            request = self._match_repair_request()
            if request:
                reason = str(normalized.get("reason", ""))
                self._retry_request(request, reason, normalized)

    # ------------------------------------------------------------------
    # Request orchestration
    def _create_request(
        self,
        mode: str,
        reason: str,
        context: Iterable[Mapping[str, object]] | None,
        details: Mapping[str, object],
    ) -> ArchitectRequest:
        architect_id = self._generate_architect_id()
        normalized_context = self._gather_context(context)
        request = ArchitectRequest(
            architect_id=architect_id,
            mode=mode,
            reason=reason,
            context=normalized_context,
            created_at=self._now(),
            details=dict(details),
            max_iterations=max(1, self.max_iterations),
        )
        self._requests[architect_id] = request
        self._write_prompt(request)
        self._publish_pulse(
            {
                "timestamp": request.created_at.isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "codex_request",
                "priority": "info",
                "payload": {
                    "architect_id": architect_id,
                    "mode": mode,
                    "reason": reason,
                    "iterations": request.iterations,
                },
            }
        )
        self._emit_ledger_event(
            {
                "event": "architect_request",
                "architect_id": architect_id,
                "mode": mode,
                "reason": reason,
                "prompt": request.prompt_path.as_posix().lstrip("/")
                if request.prompt_path
                else "",
                "iterations": request.iterations,
                "max_iterations": request.max_iterations,
            }
        )
        return request

    def _write_prompt(self, request: ArchitectRequest) -> None:
        stem = self._prompt_stem(request)
        path = self.request_dir / f"{stem}.txt"
        counter = 0
        while path.exists():
            counter += 1
            path = self.request_dir / f"{stem}_{counter}.txt"
        prompt = self._build_prompt(request)
        path.write_text(prompt, encoding="utf-8")
        metadata = request.metadata()
        metadata["prompt_path"] = path.as_posix().lstrip("/")
        metadata["context"] = request.context
        metadata["ledger_snapshot"] = list(self._ledger_buffer)
        path.with_suffix(".json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8"
        )
        prefix = self._prefix_from_stem(path.stem)
        request.codex_prefix = prefix
        request.prompt_path = path
        self._prefix_index[prefix] = request

    def _build_prompt(self, request: ArchitectRequest) -> str:
        ethics = codex_daemon.load_ethics()
        lines = [
            "You are the ArchitectDaemon for SentientOS.",
            f"Mode: {request.mode}",
            f"Reason: {request.reason}",
            "",
            SAFETY_ENVELOPE,
            "",
            "Ethics Context:",
            ethics or "No additional ethics context provided.",
            "",
        ]
        if request.details:
            lines.append("Request Details:")
            for key, value in sorted(request.details.items()):
                lines.append(f"- {key}: {value}")
            lines.append("")
        if request.context:
            lines.append("Context Events:")
            for entry in request.context:
                lines.append(f"- {json.dumps(entry, sort_keys=True)}")
            lines.append("")
        if self._ledger_buffer:
            lines.append("Recent Codex Ledger Snapshot:")
            for entry in list(self._ledger_buffer)[-10:]:
                lines.append(f"- {json.dumps(entry, sort_keys=True)}")
            lines.append("")
        if request.mode == "repair":
            lines.append("Objective: Address regressions, failing diagnostics, or anomalies.")
            lines.append("Ensure tests pass and health metrics recover.")
        elif request.mode == "expand":
            lines.append(
                "Objective: Expand SentientOS with the requested capability while"
            )
            lines.append("respecting sanctuary law and adding coverage where possible.")
        elif request.mode == "reflect":
            lines.append(
                "Objective: Perform a meta-audit, summarize risks, and propose follow-ups."
            )
        else:
            lines.append("Objective: Respond to the described situation safely and thoroughly.")
        lines.append("")
        lines.append(
            "Always generate actionable plans and patches suitable for Codex application."
        )
        return "\n".join(lines)

    def _complete_request(
        self, request: ArchitectRequest, entry: Mapping[str, object]
    ) -> None:
        request.status = "completed"
        merged = self._finalize_branch(request)
        status = "merged" if merged else "blocked"
        self._emit_ledger_event(
            {
                "event": "architect_success",
                "architect_id": request.architect_id,
                "mode": request.mode,
                "request_id": entry.get("request_id", ""),
                "files_changed": list(entry.get("files_changed", [])),
                "iterations": request.iterations,
                "merge_status": status,
            }
        )
        if merged:
            self._record_success()
        else:
            self._record_failure()
        self._prefix_index.pop(request.codex_prefix, None)

    def _retry_request(
        self,
        request: ArchitectRequest,
        reason: str,
        entry: Mapping[str, object],
    ) -> None:
        request.last_error = reason or str(entry)
        request.iterations += 1
        if request.iterations >= request.max_iterations:
            request.status = "failed"
            self._emit_ledger_event(
                {
                    "event": "architect_failure",
                    "architect_id": request.architect_id,
                    "mode": request.mode,
                    "reason": reason,
                    "iterations": request.iterations,
                }
            )
            self._record_failure()
            self._prefix_index.pop(request.codex_prefix, None)
            return
        self._emit_ledger_event(
            {
                "event": "architect_retry",
                "architect_id": request.architect_id,
                "mode": request.mode,
                "reason": reason,
                "next_iteration": request.iterations,
            }
        )
        self._prefix_index.pop(request.codex_prefix, None)
        self._write_prompt(request)

    def _surface_veil_request(
        self, request: ArchitectRequest, entry: Mapping[str, object]
    ) -> None:
        request.status = "awaiting_veil"
        payload = {
            "architect_id": request.architect_id,
            "mode": request.mode,
            "request_id": entry.get("patch_id", ""),
            "reason": request.reason,
            "files_changed": list(entry.get("files_changed", [])),
            "iterations": request.iterations,
        }
        self._emit_ledger_event(
            {
                "event": "architect_veil_pending",
                "architect_id": request.architect_id,
                "mode": request.mode,
                "request_id": payload["request_id"],
            }
        )
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "veil_request",
                "priority": "warning",
                "payload": payload,
            }
        )

    # ------------------------------------------------------------------
    # Git and CI management
    def _finalize_branch(self, request: ArchitectRequest) -> bool:
        branch = self._create_branch_name(request)
        request.branch_name = branch
        if not self._prepare_branch(branch):
            return False
        if not self._run_ci_pipeline():
            return False
        if not self._run_immutability_verifier():
            return False
        merged = self._merge_branch(branch, request)
        return merged

    def _prepare_branch(self, branch: str) -> bool:
        ok_main = self._run_git(["checkout", "main"])
        if ok_main.returncode != 0:
            self._emit_ledger_event(
                {
                    "event": "architect_branch_failed",
                    "branch": branch,
                    "reason": "checkout_main_failed",
                    "returncode": ok_main.returncode,
                }
            )
            return False
        result = self._run_git(["checkout", "-B", branch])
        if result.returncode != 0:
            self._emit_ledger_event(
                {
                    "event": "architect_branch_failed",
                    "branch": branch,
                    "reason": "create_branch_failed",
                    "returncode": result.returncode,
                }
            )
            return False
        return True

    def _run_ci_pipeline(self) -> bool:
        for command in self._ci_commands:
            result = self._run_command(command)
            if result.returncode != 0:
                self._emit_ledger_event(
                    {
                        "event": "architect_ci_failed",
                        "command": list(command),
                        "returncode": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    }
                )
                return False
        return True

    def _run_immutability_verifier(self) -> bool:
        command = list(self._immutability_command)
        result = self._run_command(command)
        if result.returncode != 0:
            self._emit_ledger_event(
                {
                    "event": "architect_immutability_failed",
                    "command": command,
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            )
            return False
        return True

    def _merge_branch(self, branch: str, request: ArchitectRequest) -> bool:
        self._run_git(["checkout", "main"])
        result = self._run_git(["merge", "--no-ff", branch])
        if result.returncode == 0:
            payload = {
                "architect_id": request.architect_id,
                "branch": branch,
                "mode": request.mode,
            }
            self._emit_ledger_event({"event": "architect_merge", **payload})
            self._publish_pulse(
                {
                    "timestamp": self._now().isoformat(),
                    "source_daemon": "ArchitectDaemon",
                    "event_type": "architect_merge",
                    "priority": "info",
                    "payload": payload,
                }
            )
            return True
        self._emit_ledger_event(
            {
                "event": "architect_merge_failed",
                "branch": branch,
                "returncode": result.returncode,
            }
        )
        return False

    def _run_git(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(list(command), capture_output=True, text=True)

    def _run_command(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(list(command), capture_output=True, text=True)

    # ------------------------------------------------------------------
    # Matching helpers
    def _match_request(self, request_id: object) -> ArchitectRequest | None:
        if not isinstance(request_id, str) or not request_id:
            return None
        for prefix, request in list(self._prefix_index.items()):
            if request_id.startswith(prefix):
                return request
        return None

    def _match_repair_request(self) -> ArchitectRequest | None:
        for request in self._requests.values():
            if request.mode == "repair" and request.status in {"submitted", "completed"}:
                return request
        return None

    # ------------------------------------------------------------------
    # Prompt helpers
    def _gather_context(
        self, context: Iterable[Mapping[str, object]] | None
    ) -> list[dict[str, object]]:
        entries = [dict(item) for item in self._context_buffer]
        if context:
            for entry in context:
                if isinstance(entry, Mapping):
                    entries.append(self._normalize_context(entry))
        return entries[-25:]

    def _normalize_context(self, entry: Mapping[str, object]) -> dict[str, object]:
        normalized: dict[str, object] = {}
        if "source" in entry:
            normalized["source"] = str(entry.get("source"))
        elif "source_daemon" in entry:
            normalized["source"] = str(entry.get("source_daemon"))
        if "event_type" in entry:
            normalized["event_type"] = str(entry.get("event_type"))
        if "priority" in entry:
            normalized["priority"] = str(entry.get("priority"))
        if "timestamp" in entry:
            normalized["timestamp"] = str(entry.get("timestamp"))
        payload = entry.get("payload")
        if isinstance(payload, Mapping):
            normalized["payload"] = _normalize_mapping(payload)
        elif payload is not None:
            normalized["payload"] = payload
        for key in ("reason", "detail", "summary"):
            if key in entry:
                normalized[key] = entry[key]
        return normalized

    def _prompt_stem(self, request: ArchitectRequest) -> str:
        stem = request.architect_id
        if request.iterations:
            stem = f"{stem}_iter{request.iterations:02d}"
        return stem

    def _prefix_from_stem(self, stem: str) -> str:
        token = _sanitize_token(stem)
        return f"expand_{token}_"

    def _generate_architect_id(self) -> str:
        return f"architect_{self._now().strftime('%Y%m%d_%H%M%S')}"

    # ------------------------------------------------------------------
    # Ledger & pulse helpers
    def _emit_ledger_event(self, event: Mapping[str, object]) -> None:
        payload = dict(event)
        payload.setdefault("ts", self._now().strftime("%Y-%m-%d %H:%M:%S"))
        payload.setdefault("source", "ArchitectDaemon")
        try:
            append_json(self.ledger_path, payload)
        except Exception:
            pass
        if self._ledger_sink:
            try:
                self._ledger_sink(dict(payload))
            except Exception:
                pass

    def _publish_pulse(self, event: Mapping[str, object]) -> None:
        try:
            self._pulse_publisher(dict(event))
        except Exception:
            pass

    def _normalize_pulse_event(
        self, event: Mapping[str, object]
    ) -> dict[str, object] | None:
        source = event.get("source_daemon")
        event_type = event.get("event_type")
        if not isinstance(source, str) or not isinstance(event_type, str):
            return None
        normalized = {
            "timestamp": str(event.get("timestamp", self._now().isoformat())),
            "source": source,
            "event_type": event_type,
        }
        priority = event.get("priority")
        if isinstance(priority, str):
            normalized["priority"] = priority
        payload = event.get("payload")
        if isinstance(payload, Mapping):
            normalized["payload"] = _normalize_mapping(payload)
        return normalized

    def _normalize_ledger_entry(
        self, entry: Mapping[str, object]
    ) -> dict[str, object] | None:
        event = entry.get("event")
        if not isinstance(event, str) or not event:
            return None
        normalized: dict[str, object] = {"event": event}
        for key in (
            "request_id",
            "patch_id",
            "reason",
            "files_changed",
            "codex_mode",
            "iterations",
            "failure_reason",
        ):
            if key in entry:
                normalized[key] = entry[key]
        return normalized

    def _create_branch_name(self, request: ArchitectRequest) -> str:
        timestamp = self._now().strftime("%Y%m%d_%H%M%S")
        token = _sanitize_token(request.architect_id)
        return f"architect/{token}_{timestamp}"
