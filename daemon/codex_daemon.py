from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
from typing import Any, Iterable, Mapping, Sequence

from sentientos import immutability
from sentientos.daemons import pulse_bus

CODEX_MODE = "observe"
CODEX_MAX_ITERATIONS = 1
CODEX_FOCUS = "pytest"
CODEX_SUGGEST_DIR = Path("/glow/codex_suggestions")
CODEX_PATCH_DIR = CODEX_SUGGEST_DIR
CODEX_REASONING_DIR = Path("/daemon/logs/codex_reasoning")
CODEX_LOG = Path("/daemon/logs/codex.jsonl")
CODEX_CONFIRM_PATTERNS: list[str] = []
CODEX_NOTIFY: list[str] = []
MONITORING_METRICS_PATH = Path("/glow/monitoring/metrics.jsonl")

EXPAND_REQUEST_DIR = Path("/glow/codex_requests")
EXPAND_ARCHIVE_DIR = EXPAND_REQUEST_DIR / "archive"
EXPAND_MAX_BYTES = 50 * 1024
PROJECT_ROOT = Path(os.getenv("CODEX_PROJECT_ROOT", Path.cwd())).resolve()

def _workspace_root() -> Path:
    if isinstance(PROJECT_ROOT, Path):
        return PROJECT_ROOT
    return Path(str(PROJECT_ROOT)).resolve()


def _normalize_repo_path(path: str) -> str:
    text = str(path).replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    if text.startswith("/"):
        text = text[1:]
    return text


def _is_off_limits(path: str) -> bool:
    candidate = _normalize_repo_path(path)
    if not candidate:
        return True
    if candidate.startswith("vow/"):
        return True
    if immutability.is_protected_path(candidate):
        return True
    if candidate.startswith("NEWLEGACY"):
        return True
    return False


def _resolve_workspace_path(path: str) -> Path:
    candidate = _normalize_repo_path(path)
    if not candidate:
        raise ValueError("empty_path")
    parts = Path(candidate).parts
    if any(part == ".." for part in parts):
        raise ValueError("parent_traversal_not_allowed")
    base = _workspace_root().resolve()
    target = base.joinpath(Path(candidate))
    resolved = target.resolve(strict=False)
    if not str(resolved).startswith(str(base)):
        raise ValueError("path_outside_workspace")
    return resolved


def _apply_file_mapping(mapping: Mapping[str, object]) -> list[str]:
    if not isinstance(mapping, Mapping):
        raise ValueError("mapping_not_object")
    changed: list[str] = []
    base = _workspace_root().resolve()
    for raw_path, payload in mapping.items():
        if not isinstance(raw_path, str):
            raise ValueError("invalid_path_key")
        if not isinstance(payload, str):
            raise ValueError("invalid_file_content")
        target = _resolve_workspace_path(raw_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding="utf-8")
        rel = target.resolve(strict=False).relative_to(base)
        changed.append(rel.as_posix())
    return sorted(set(changed))


MANIFEST_PATH = immutability.DEFAULT_MANIFEST_PATH
MANIFEST_AUTO_UPDATE = (
    os.getenv("CODEX_MANIFEST_AUTO_UPDATE", "1").strip().lower() not in {"0", "false"}
)

LOCAL_PEER_NAME = os.getenv("CODEX_LOCAL_PEER", "local")
FEDERATED_AUTO_APPLY = (
    os.getenv("CODEX_FEDERATED_AUTO_APPLY", "0").strip().lower() not in {"0", "false"}
)


def load_ethics() -> str:
    """Return additional safety context for predictive prompts."""

    path_value = os.getenv("CODEX_ETHICS_PATH")
    if path_value:
        try:
            return Path(path_value).read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return ""
    return os.getenv("CODEX_ETHICS_TEXT", "").strip()


def parse_diff_files(diff_output: str) -> list[str]:
    files: list[str] = []
    for line in diff_output.splitlines():
        if line.startswith("+++ b/"):
            candidate = line[6:].strip()
            if candidate and candidate != "/dev/null":
                files.append(candidate)
    return files


def parse_failing_tests(summary: str) -> list[str]:
    tests: list[str] = []
    for line in summary.splitlines():
        line = line.strip()
        if line.startswith("FAILED "):
            tests.append(line[7:].split()[0])
    return tests


def is_safe(files_changed: Iterable[str]) -> bool:
    patterns = [p.strip() for p in CODEX_CONFIRM_PATTERNS]
    if not patterns:
        return True
    for path in files_changed:
        for pattern in patterns:
            if not pattern:
                continue
            if pattern in path:
                return False
    return True


def _requires_manual_confirmation(files_changed: Sequence[str]) -> bool:
    if not files_changed:
        return False
    if not is_safe(files_changed):
        return True
    for path in files_changed:
        normalized = str(path).replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        if not normalized:
            continue
        if immutability.is_protected_path(normalized):
            return True
        if normalized.startswith("vow/"):
            return True
    return False


def _iso_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ledger_timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _sanitize_token(value: str) -> str:
    token = value.strip()
    if not token:
        return "token"
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in token)


def _is_valid_request_name(name: str) -> bool:
    if "/" in name or "\\" in name:
        return False
    if ".." in name:
        return False
    return True


def _build_expand_prompt(task: str, context: str | None) -> str:
    ethics = load_ethics()
    lines = [
        "You are the SentientOS Codex expansion assistant operating in expand mode.",
        "Follow all sanctuary ethics, privilege boundaries, and safety guardrails.",
        "",
        "Ethics Context:",
        ethics or "None provided.",
        "",
        "Task:",
        task.strip(),
    ]
    if context:
        lines.extend(["", "Additional Context:", context.strip()])
    lines.extend(
        [
            "",
            "Guardrails:",
            "- Do not touch /vow/, NEWLEGACY, or privileged files.",
            "- Keep changes minimal, transparent, and reversible.",
            "- Prefer additive expansions that respect existing tests.",
            "",
            "Output Instructions:",
            "Respond with either a unified diff (preferred) or a JSON object mapping file paths to file contents.",
            "All paths must be relative to the repository root.",
        ]
    )
    return "\n".join(lines)


def _generate_expand_request_id(source_name: str) -> str:
    token = _sanitize_token(Path(source_name).stem or "request")
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:6]
    return f"expand_{token}_{timestamp}_{suffix}"


def _archive_request_file(path: Path, request_id: str) -> Path:
    EXPAND_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    destination = EXPAND_ARCHIVE_DIR / f"{request_id}{path.suffix}"
    counter = 0
    while destination.exists():
        counter += 1
        destination = EXPAND_ARCHIVE_DIR / f"{request_id}_{counter}{path.suffix}"
    path.rename(destination)
    return destination


def _archive_codex_response(request_id: str, content: str, *, suffix: str) -> Path:
    EXPAND_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    response_path = EXPAND_ARCHIVE_DIR / f"{request_id}_response{suffix}"
    response_path.write_text(content, encoding="utf-8")
    return response_path


def _write_expand_trace(
    request_id: str,
    *,
    prompt: str,
    response: str,
    task: str,
    context: str | None,
) -> Path:
    CODEX_REASONING_DIR.mkdir(parents=True, exist_ok=True)
    trace_path = CODEX_REASONING_DIR / f"expand_{request_id}.json"
    trace = {
        "ts": _iso_timestamp(),
        "request_id": request_id,
        "prompt": prompt,
        "response": response,
        "task": task,
        "context": context or "",
        "codex_mode": CODEX_MODE,
    }
    trace_path.write_text(json.dumps(trace, indent=2, sort_keys=True), encoding="utf-8")
    return trace_path


def _log_expand_entry(entry: dict[str, object], ledger_queue: Queue | None) -> None:
    log_activity(dict(entry))
    if ledger_queue is not None:
        ledger_queue.put(dict(entry))


def _publish_expand_request(
    request_id: str,
    *,
    request_file: Path,
    task: str,
    context: str | None,
    size: int,
) -> None:
    payload = {
        "request_id": request_id,
        "request_file": request_file.as_posix().lstrip("/"),
        "task": task,
        "context": context or "",
        "size_bytes": size,
        "codex_mode": CODEX_MODE,
    }
    pulse_bus.publish(
        {
            "timestamp": _iso_timestamp(),
            "source_daemon": "CodexDaemon",
            "event_type": "expand_request",
            "priority": "info",
            "payload": payload,
        }
    )


def _publish_expand_result(
    request_id: str,
    *,
    status: str,
    reason: str | None,
    files_changed: Sequence[str],
    response_format: str,
) -> None:
    payload = {
        "request_id": request_id,
        "status": status,
        "reason": reason or "",
        "files_changed": list(files_changed),
        "response_format": response_format,
        "codex_mode": CODEX_MODE,
    }
    pulse_bus.publish(
        {
            "timestamp": _iso_timestamp(),
            "source_daemon": "CodexDaemon",
            "event_type": "expand_result",
            "priority": "info",
            "payload": payload,
        }
    )


def _queue_expand_veil(
    request_id: str,
    patch_path: Path,
    files_changed: Sequence[str],
    task: str,
    ledger_queue: Queue | None,
    *,
    response_format: str,
) -> None:
    metadata = {
        "patch_id": request_id,
        "patch_path": patch_path.as_posix().lstrip("/"),
        "scope": "local",
        "requires_confirmation": True,
        "status": "pending",
        "files_changed": list(files_changed),
        "codex_mode": CODEX_MODE,
        "timestamp": _iso_timestamp(),
        "response_format": response_format,
        "task": task,
    }
    metadata_path = patch_path.with_suffix("").with_suffix(".veil.json")
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    pulse_bus.publish(
        {
            "timestamp": _iso_timestamp(),
            "source_daemon": "CodexDaemon",
            "event_type": "veil_request",
            "priority": "warning",
            "payload": dict(metadata),
        }
    )
    ledger_entry = {
        "ts": _ledger_timestamp(),
        "event": "veil_pending",
        "patch_id": request_id,
        "files_changed": list(files_changed),
        "codex_mode": CODEX_MODE,
        "scope": "local",
    }
    _log_expand_entry(ledger_entry, ledger_queue)


def _load_expand_request(path: Path) -> tuple[str, str | None]:
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix == ".json":
        data = json.loads(text)
        if not isinstance(data, Mapping):
            raise ValueError("json_request_not_object")
        task = data.get("task")
        if not isinstance(task, str) or not task.strip():
            raise ValueError("missing_task")
        context = data.get("context")
        context_text = context if isinstance(context, str) and context.strip() else None
        return task.strip(), context_text
    if suffix == ".txt":
        task = text.strip()
        if not task:
            raise ValueError("missing_task")
        return task, None
    raise ValueError("unsupported_request_format")


def _handle_expand_request(path: Path, ledger_queue: Queue | None) -> dict[str, object]:
    request_id = _generate_expand_request_id(path.name)
    request_size = path.stat().st_size
    task = ""
    context: str | None = None
    response_format = "diff"
    files_changed: list[str] = []
    archived_request: Path | None = None

    if not _is_valid_request_name(path.name):
        archived_request = _archive_request_file(path, request_id)
        _publish_expand_request(
            request_id,
            request_file=archived_request,
            task=task,
            context=context,
            size=request_size,
        )
        entry = {
            "ts": _ledger_timestamp(),
            "event": "self_expand_rejected",
            "request_id": request_id,
            "reason": "invalid_name",
            "files_changed": files_changed,
            "codex_mode": CODEX_MODE,
        }
        _publish_expand_result(request_id, status="rejected", reason="invalid_name", files_changed=files_changed, response_format=response_format)
        _log_expand_entry(entry, ledger_queue)
        return entry

    if request_size > EXPAND_MAX_BYTES:
        archived_request = _archive_request_file(path, request_id)
        _publish_expand_request(
            request_id,
            request_file=archived_request,
            task=task,
            context=context,
            size=request_size,
        )
        entry = {
            "ts": _ledger_timestamp(),
            "event": "self_expand_rejected",
            "request_id": request_id,
            "reason": "request_too_large",
            "files_changed": files_changed,
            "codex_mode": CODEX_MODE,
        }
        _publish_expand_result(request_id, status="rejected", reason="request_too_large", files_changed=files_changed, response_format=response_format)
        _log_expand_entry(entry, ledger_queue)
        return entry

    try:
        task, context = _load_expand_request(path)
    except Exception:
        archived_request = _archive_request_file(path, request_id)
        _publish_expand_request(
            request_id,
            request_file=archived_request,
            task=task,
            context=context,
            size=request_size,
        )
        entry = {
            "ts": _ledger_timestamp(),
            "event": "self_expand_rejected",
            "request_id": request_id,
            "reason": "invalid_request",
            "files_changed": files_changed,
            "codex_mode": CODEX_MODE,
        }
        _publish_expand_result(request_id, status="rejected", reason="invalid_request", files_changed=files_changed, response_format=response_format)
        _log_expand_entry(entry, ledger_queue)
        return entry

    archived_request = _archive_request_file(path, request_id)
    _publish_expand_request(
        request_id,
        request_file=archived_request,
        task=task,
        context=context,
        size=request_size,
    )

    prompt = _build_expand_prompt(task, context)
    proc = subprocess.run(["codex", "exec", prompt], capture_output=True, text=True)
    codex_output = proc.stdout
    if not codex_output.strip():
        _publish_expand_result(request_id, status="rejected", reason="empty_response", files_changed=files_changed, response_format=response_format)
        entry = {
            "ts": _ledger_timestamp(),
            "event": "self_expand_rejected",
            "request_id": request_id,
            "reason": "empty_response",
            "files_changed": files_changed,
            "codex_mode": CODEX_MODE,
        }
        _log_expand_entry(entry, ledger_queue)
        return entry

    trace_path = _write_expand_trace(
        request_id,
        prompt=prompt,
        response=codex_output,
        task=task,
        context=context,
    )

    suggestion_path = CODEX_SUGGEST_DIR / f"{request_id}.diff"
    mapping: Mapping[str, object] | None = None
    try:
        parsed = json.loads(codex_output)
        if isinstance(parsed, Mapping):
            mapping = parsed
    except json.JSONDecodeError:
        mapping = None

    if mapping is not None:
        response_format = "json_mapping"
        files_changed = [
            _normalize_repo_path(path_key)
            for path_key in mapping.keys()
            if isinstance(path_key, str)
        ]
        files_changed = [path for path in files_changed if path]
        suggestion_path = CODEX_SUGGEST_DIR / f"{request_id}.json"
        suggestion_path.parent.mkdir(parents=True, exist_ok=True)
        suggestion_path.write_text(json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8")
        _archive_codex_response(request_id, codex_output, suffix=".json")
    else:
        files_changed = parse_diff_files(codex_output)
        suggestion_path.parent.mkdir(parents=True, exist_ok=True)
        suggestion_path.write_text(codex_output, encoding="utf-8")
        _archive_codex_response(request_id, codex_output, suffix=".diff")

    files_changed = sorted({_normalize_repo_path(path) for path in files_changed if path})
    suggest_entry = {
        "ts": _ledger_timestamp(),
        "event": "self_expand_suggested",
        "request_id": request_id,
        "task": task,
        "files_changed": list(files_changed),
        "codex_mode": CODEX_MODE,
        "response_format": response_format,
        "reasoning_trace": trace_path.as_posix().lstrip("/"),
    }
    _log_expand_entry(suggest_entry, ledger_queue)

    if not files_changed:
        _publish_expand_result(request_id, status="rejected", reason="no_changes", files_changed=files_changed, response_format=response_format)
        entry = {
            "ts": _ledger_timestamp(),
            "event": "self_expand_rejected",
            "request_id": request_id,
            "reason": "no_changes",
            "files_changed": files_changed,
            "codex_mode": CODEX_MODE,
            "response_format": response_format,
        }
        _log_expand_entry(entry, ledger_queue)
        return entry

    if any(_is_off_limits(path) for path in files_changed):
        _publish_expand_result(request_id, status="rejected", reason="off_limits", files_changed=files_changed, response_format=response_format)
        entry = {
            "ts": _ledger_timestamp(),
            "event": "self_expand_rejected",
            "request_id": request_id,
            "reason": "off_limits",
            "files_changed": list(files_changed),
            "codex_mode": CODEX_MODE,
            "response_format": response_format,
        }
        _log_expand_entry(entry, ledger_queue)
        return entry

    requires_confirmation = not is_safe(files_changed)
    if requires_confirmation:
        _queue_expand_veil(
            request_id,
            suggestion_path,
            files_changed,
            task,
            ledger_queue,
            response_format=response_format,
        )
        _publish_expand_result(request_id, status="veil_pending", reason="veil", files_changed=files_changed, response_format=response_format)
        entry = {
            "ts": _ledger_timestamp(),
            "event": "self_expand_rejected",
            "request_id": request_id,
            "reason": "veil",
            "files_changed": list(files_changed),
            "codex_mode": CODEX_MODE,
            "response_format": response_format,
        }
        _log_expand_entry(entry, ledger_queue)
        return entry

    success = False
    verification = False
    if response_format == "diff":
        success = bool(apply_patch(codex_output))
        changed_files = list(files_changed)
    else:
        try:
            changed_files = _apply_file_mapping(mapping or {})
            success = True
        except Exception:
            changed_files = list(files_changed)
            success = False

    if not success:
        _publish_expand_result(request_id, status="rejected", reason="patch_apply_failed", files_changed=files_changed, response_format=response_format)
        entry = {
            "ts": _ledger_timestamp(),
            "event": "self_expand_rejected",
            "request_id": request_id,
            "reason": "patch_apply_failed",
            "files_changed": list(files_changed),
            "codex_mode": CODEX_MODE,
            "response_format": response_format,
        }
        _log_expand_entry(entry, ledger_queue)
        return entry

    queue = ledger_queue if ledger_queue is not None else Queue()
    verification = bool(run_ci(queue))
    if not verification:
        _publish_expand_result(request_id, status="rejected", reason="ci_failed", files_changed=changed_files, response_format=response_format)
        entry = {
            "ts": _ledger_timestamp(),
            "event": "self_expand_rejected",
            "request_id": request_id,
            "reason": "ci_failed",
            "files_changed": list(changed_files),
            "codex_mode": CODEX_MODE,
            "response_format": response_format,
        }
        _log_expand_entry(entry, ledger_queue)
        return entry

    subprocess.run(["git", "add", "-A"], check=False)
    subprocess.run(["git", "commit", "-m", "[codex:self_expand]"], check=False)

    result_entry = {
        "ts": _ledger_timestamp(),
        "event": "self_expand",
        "request_id": request_id,
        "task": task,
        "files_changed": list(changed_files),
        "verification_result": verification,
        "codex_mode": CODEX_MODE,
        "response_format": response_format,
        "reasoning_trace": trace_path.as_posix().lstrip("/"),
    }
    _log_expand_entry(result_entry, ledger_queue)
    _publish_expand_result(
        request_id,
        status="applied",
        reason=None,
        files_changed=changed_files,
        response_format=response_format,
    )
    _reconcile_manifest(changed_files, ledger_queue, source_event="self_expand")
    return result_entry


def _process_expand_requests(ledger_queue: Queue | None) -> dict[str, object] | None:
    request_dir = EXPAND_REQUEST_DIR
    if not request_dir.exists():
        return None
    candidates = sorted(path for path in request_dir.iterdir() if path.is_file())
    for candidate in candidates:
        if candidate.suffix.lower() not in {".json", ".txt"}:
            continue
        return _handle_expand_request(candidate, ledger_queue)
    return None


def apply_patch(diff_output: str) -> bool:
    return False


def _call_apply_patch(diff_output: str, *, label: str | None = None) -> dict[str, object]:
    try:
        applied = bool(apply_patch(diff_output))
        return {
            "applied": applied,
            "archived_diff": None,
            "restored_repo": False,
            "failure_reason": None,
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "applied": False,
            "archived_diff": None,
            "restored_repo": True,
            "failure_reason": str(exc),
        }


def run_diagnostics() -> tuple[bool, str, int]:
    return True, "", 0


def run_ci(queue: Queue) -> bool:
    return True


def log_activity(entry: dict[str, object]) -> None:
    CODEX_LOG.parent.mkdir(parents=True, exist_ok=True)
    with CODEX_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def send_notifications(entry: dict[str, object]) -> None:  # pragma: no cover - stub
    return None


def _filtered_manifest_paths(files: Sequence[str]) -> list[str]:
    filtered: list[str] = []
    for path in files:
        if not path:
            continue
        if immutability.is_protected_path(path):
            continue
        filtered.append(path)
    return filtered


def _reconcile_manifest(
    files: Sequence[str],
    ledger_queue: Queue | None,
    *,
    source_event: str,
) -> dict[str, object] | None:
    if not MANIFEST_AUTO_UPDATE:
        return None
    filtered = _filtered_manifest_paths(list(files))
    if not filtered:
        return None
    try:
        manifest = immutability.update_manifest(filtered, manifest_path=MANIFEST_PATH)
    except Exception as exc:  # pragma: no cover - surfaced via ledger
        failure = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": "manifest_reconcile_failed",
            "files_changed": filtered,
            "reason": str(exc),
            "manifest_path": str(MANIFEST_PATH),
            "source_event": source_event,
        }
        if ledger_queue is not None:
            ledger_queue.put(failure)
        return None

    now = datetime.now(timezone.utc).isoformat()
    ledger_entry = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "event": "manifest_reconciled",
        "files_changed": filtered,
        "manifest_path": str(MANIFEST_PATH),
        "signature": manifest.get("signature", ""),
        "source_event": source_event,
    }
    if ledger_queue is not None:
        ledger_queue.put(ledger_entry)
    pulse_bus.publish(
        {
            "timestamp": manifest.get("generated", now),
            "source_daemon": "CodexDaemon",
            "event_type": "manifest_update",
            "priority": "info",
            "payload": {
                "files": filtered,
                "signature": manifest.get("signature", ""),
                "manifest_path": str(MANIFEST_PATH),
                "source_event": source_event,
            },
        }
    )
    return manifest


class _PredictiveRepairManager:
    def __init__(self) -> None:
        self.suggestion_dir = CODEX_SUGGEST_DIR
        self.metrics_path = MONITORING_METRICS_PATH

    def handle_alert(self, event: Mapping[str, object], ledger_queue: Queue | None = None) -> None:
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            return
        prompt = self._build_prompt(event, payload)
        diff_text = self._invoke_codex(prompt)
        if not diff_text.strip():
            return
        scope, target_peer = self._determine_scope(event)
        origin_peer = str(event.get("source_peer") or LOCAL_PEER_NAME)
        patch_id = self._build_patch_id(scope, target_peer if scope == "federated" else LOCAL_PEER_NAME)
        diff_path = self._write_diff(patch_id, diff_text)
        files_changed = sorted(set(parse_diff_files(diff_text)))
        analysis_window = self._analysis_window(payload)
        anomaly_pattern = self._anomaly_pattern(payload)
        target_daemon = self._target_daemon(payload)
        suggestion_entry: dict[str, Any] = {
            "ts": _ledger_timestamp(),
            "event": "self_predict_suggested" if scope == "local" else "federated_predictive_event",
            "status": "suggested",
            "scope": scope,
            "patch_id": patch_id,
            "patch_path": diff_path.as_posix().lstrip("/"),
            "files_changed": files_changed,
            "analysis_window": analysis_window,
            "anomaly_pattern": anomaly_pattern,
            "target_daemon": target_daemon,
            "codex_mode": CODEX_MODE,
            "source_peer": LOCAL_PEER_NAME,
            "origin_peer": origin_peer,
            "target_peer": "" if scope == "local" else target_peer,
        }
        if scope == "local":
            suggestion_entry["prompt"] = prompt
        log_activity(dict(suggestion_entry))
        if ledger_queue is not None:
            ledger_queue.put(dict(suggestion_entry))

        requires_confirmation = _requires_manual_confirmation(files_changed)
        if scope == "local":
            if requires_confirmation:
                self._append_restriction_notice(diff_path, "manual confirmation required")
                metadata = self._create_veil_metadata(
                    patch_id,
                    diff_path,
                    files_changed,
                    scope,
                    analysis_window,
                    anomaly_pattern,
                    target_daemon,
                    LOCAL_PEER_NAME,
                    LOCAL_PEER_NAME,
                )
                self._publish_veil_request(metadata, ledger_queue)
                return
            if CODEX_MODE == "expand" and files_changed:
                self._auto_apply_local(
                    diff_text,
                    files_changed,
                    patch_id,
                    analysis_window,
                    anomaly_pattern,
                    target_daemon,
                    ledger_queue,
                )
            return

        federated_payload = self._build_federated_payload(
            patch_id,
            diff_path,
            diff_text,
            files_changed,
            analysis_window,
            anomaly_pattern,
            target_daemon,
            target_peer,
            requires_confirmation,
            payload,
            origin_peer,
        )
        pulse_bus.publish(
            {
                "timestamp": _iso_timestamp(),
                "source_daemon": "CodexDaemon",
                "event_type": "predictive_suggestion",
                "priority": "info",
                "source_peer": LOCAL_PEER_NAME,
                "payload": federated_payload,
            }
        )

    def _build_prompt(self, event: Mapping[str, object], payload: Mapping[str, object]) -> str:
        daemon_name = self._target_daemon(payload) or "system"
        anomaly = self._anomaly_pattern(payload) or "anomaly"
        window = self._analysis_window(payload)
        ethics = load_ethics()
        summary_lines = [
            f"Codex predictive repair request for {daemon_name}.",
            "",
            "Safety Context:",
            ethics or "None provided.",
            "",
            "Alert Summary:",
            f"- anomaly: {anomaly}",
        ]
        observed = payload.get("observed") or payload.get("count")
        if observed is not None:
            summary_lines.append(f"- observed: {observed}")
        threshold = payload.get("threshold")
        if threshold is not None:
            summary_lines.append(f"- threshold: {threshold}")
        summary_lines.append(f"- analysis_window: {window}")
        source_peer = str(event.get("source_peer") or LOCAL_PEER_NAME)
        summary_lines.append(f"- originating_peer: {source_peer}")
        summary_lines.extend(
            [
                "",
                "Generate a minimal unified diff patch that addresses the anomaly.",
                "Only output the diff with paths relative to the repository root.",
            ]
        )
        return "\n".join(summary_lines)

    def _invoke_codex(self, prompt: str) -> str:
        proc = subprocess.run(["codex", "exec", prompt], capture_output=True, text=True)
        return proc.stdout

    def _determine_scope(self, event: Mapping[str, object]) -> tuple[str, str]:
        source_peer = str(event.get("source_peer") or "")
        if source_peer and source_peer != LOCAL_PEER_NAME:
            return "federated", source_peer
        return "local", LOCAL_PEER_NAME

    def _build_patch_id(self, scope: str, peer: str | None) -> str:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        suffix = uuid.uuid4().hex[:6]
        peer_token = _sanitize_token(peer or LOCAL_PEER_NAME)
        prefix = f"predictive_{peer_token}"
        return f"{prefix}_{timestamp}_{suffix}"

    def _write_diff(self, patch_id: str, diff_text: str) -> Path:
        self.suggestion_dir.mkdir(parents=True, exist_ok=True)
        path = self.suggestion_dir / f"{patch_id}.diff"
        path.write_text(diff_text, encoding="utf-8")
        return path

    def _analysis_window(self, payload: Mapping[str, object]) -> str:
        window = payload.get("analysis_window")
        if isinstance(window, str) and window:
            return window
        window_seconds = payload.get("window_seconds")
        if isinstance(window_seconds, (int, float)) and window_seconds > 0:
            if window_seconds % 60 == 0:
                return f"{int(window_seconds // 60)}m"
            return f"{int(window_seconds)}s"
        return "unknown"

    def _anomaly_pattern(self, payload: Mapping[str, object]) -> str:
        value = payload.get("anomaly_pattern") or payload.get("event_type") or payload.get("name")
        return str(value or "")

    def _target_daemon(self, payload: Mapping[str, object]) -> str:
        value = payload.get("target_daemon") or payload.get("source_daemon")
        return str(value or "")

    def _append_restriction_notice(self, path: Path, reason: str) -> None:
        try:
            original = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            original = ""
        notice = f"# Predictive patch rejected: {reason}\n\n"
        path.write_text(notice + original, encoding="utf-8")

    def _create_veil_metadata(
        self,
        patch_id: str,
        diff_path: Path,
        files_changed: Sequence[str],
        scope: str,
        analysis_window: str,
        anomaly_pattern: str,
        target_daemon: str,
        source_peer: str,
        target_peer: str,
    ) -> dict[str, object]:
        metadata: dict[str, object] = {
            "patch_id": patch_id,
            "patch_path": diff_path.as_posix().lstrip("/"),
            "scope": scope,
            "anomaly_pattern": anomaly_pattern,
            "analysis_window": analysis_window,
            "requires_confirmation": True,
            "status": "pending",
            "files_changed": list(files_changed),
            "source_peer": source_peer,
            "target_peer": target_peer,
            "target_daemon": target_daemon,
            "timestamp": _iso_timestamp(),
            "codex_mode": CODEX_MODE,
        }
        metadata_path = diff_path.with_suffix("").with_suffix(".veil.json")
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
        return metadata

    def _publish_veil_request(self, metadata: Mapping[str, object], ledger_queue: Queue | None) -> None:
        veil_event = {
            "timestamp": _iso_timestamp(),
            "source_daemon": "CodexDaemon",
            "event_type": "veil_request",
            "priority": "warning",
            "payload": dict(metadata),
        }
        pulse_bus.publish(veil_event)
        ledger_entry: dict[str, Any] = {
            "ts": _ledger_timestamp(),
            "event": "veil_pending",
            "patch_id": metadata.get("patch_id", ""),
            "scope": metadata.get("scope", "local"),
            "status": metadata.get("status", "pending"),
            "requires_confirmation": True,
            "files_changed": list(metadata.get("files_changed", [])),
            "analysis_window": metadata.get("analysis_window", ""),
            "anomaly_pattern": metadata.get("anomaly_pattern", ""),
            "source_peer": metadata.get("source_peer", ""),
            "target_peer": metadata.get("target_peer", ""),
        }
        log_activity(dict(ledger_entry))
        if ledger_queue is not None:
            ledger_queue.put(dict(ledger_entry))

    def _auto_apply_local(
        self,
        diff_text: str,
        files_changed: Sequence[str],
        patch_id: str,
        analysis_window: str,
        anomaly_pattern: str,
        target_daemon: str,
        ledger_queue: Queue | None,
    ) -> None:
        applied = bool(apply_patch(diff_text))
        verification = False
        if applied:
            queue = ledger_queue if ledger_queue is not None else Queue()
            verification = bool(run_ci(queue))
        entry: dict[str, Any] = {
            "ts": _ledger_timestamp(),
            "event": "self_predict_applied" if applied else "self_predict_failed",
            "status": "applied" if applied and verification else "failed",
            "verification_result": verification if applied else False,
            "patch_id": patch_id,
            "files_changed": list(files_changed),
            "analysis_window": analysis_window,
            "anomaly_pattern": anomaly_pattern,
            "target_daemon": target_daemon,
            "codex_mode": CODEX_MODE,
            "scope": "local",
        }
        log_activity(dict(entry))
        if ledger_queue is not None:
            ledger_queue.put(dict(entry))
        pulse_bus.publish(
            {
                "timestamp": _iso_timestamp(),
                "source_daemon": "CodexDaemon",
                "event_type": "predictive_patch",
                "priority": "info",
                "payload": {
                    "patch_id": patch_id,
                    "scope": "local",
                    "status": entry["status"],
                    "files_changed": list(files_changed),
                    "analysis_window": analysis_window,
                    "anomaly_pattern": anomaly_pattern,
                    "verification_result": entry.get("verification_result", False),
                },
            }
        )
        if applied and verification:
            record_self_predict_applied(files_changed, ledger_queue)

    def _build_federated_payload(
        self,
        patch_id: str,
        diff_path: Path,
        diff_text: str,
        files_changed: Sequence[str],
        analysis_window: str,
        anomaly_pattern: str,
        target_daemon: str,
        target_peer: str,
        requires_confirmation: bool,
        alert_payload: Mapping[str, object],
        origin_peer: str,
    ) -> dict[str, object]:
        anomaly_info = {
            "event_type": anomaly_pattern,
            "observed": alert_payload.get("observed") or alert_payload.get("count"),
            "threshold": alert_payload.get("threshold"),
        }
        triggering = {k: v for k, v in anomaly_info.items() if v is not None}
        return {
            "patch_id": patch_id,
            "patch_path": diff_path.as_posix().lstrip("/"),
            "scope": "federated",
            "status": "suggested",
            "source_peer": LOCAL_PEER_NAME,
            "origin_peer": origin_peer,
            "target_peer": target_peer,
            "target_daemon": target_daemon,
            "anomaly_pattern": anomaly_pattern,
            "analysis_window": analysis_window,
            "files_changed": list(files_changed),
            "requires_confirmation": requires_confirmation,
            "triggering_anomaly": triggering,
            "patch_diff": diff_text,
            "codex_mode": CODEX_MODE,
        }


def _process_predictive_suggestion(
    event: Mapping[str, object], ledger_queue: Queue | None = None
) -> None:
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        return
    target_peer = str(payload.get("target_peer") or event.get("target_peer") or "")
    if target_peer and target_peer not in {LOCAL_PEER_NAME, "", "local"}:
        return
    diff_text = payload.get("patch_diff")
    if not isinstance(diff_text, str) or not diff_text.strip():
        return
    files_changed = sorted({str(path) for path in parse_diff_files(diff_text)})

    analysis_window = payload.get("analysis_window")
    if not isinstance(analysis_window, str) or not analysis_window:
        window_seconds = payload.get("window_seconds")
        if isinstance(window_seconds, (int, float)) and window_seconds > 0:
            if window_seconds % 60 == 0:
                analysis_window = f"{int(window_seconds // 60)}m"
            else:
                analysis_window = f"{int(window_seconds)}s"
        else:
            analysis_window = "unknown"

    anomaly_pattern = str(
        payload.get("anomaly_pattern")
        or payload.get("event_type")
        or payload.get("name")
        or ""
    )
    source_peer = str(payload.get("source_peer") or event.get("source_peer") or "")
    target_daemon = str(payload.get("target_daemon") or payload.get("source_daemon") or "")

    suggestion_dir = CODEX_SUGGEST_DIR
    suggestion_dir.mkdir(parents=True, exist_ok=True)
    peer_token = _sanitize_token(source_peer or "remote")
    patch_id = f"peer_{peer_token}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
    requires_confirmation = _requires_manual_confirmation(files_changed)

    diff_path = suggestion_dir / f"{patch_id}.diff"
    diff_path.write_text(diff_text, encoding="utf-8")

    entry: dict[str, Any] = {
        "ts": _ledger_timestamp(),
        "event": "federated_predictive_event",
        "status": "suggested",
        "patch_id": patch_id,
        "files_changed": files_changed,
        "analysis_window": analysis_window,
        "anomaly_pattern": anomaly_pattern,
        "source_peer": source_peer,
        "target_peer": LOCAL_PEER_NAME,
        "target_daemon": target_daemon,
        "requires_confirmation": requires_confirmation,
    }
    log_activity(dict(entry))
    if ledger_queue is not None:
        ledger_queue.put(dict(entry))

    update_payload = {
        "patch_id": patch_id,
        "patch_path": diff_path.as_posix().lstrip("/"),
        "scope": "federated",
        "status": "suggested",
        "source_peer": source_peer,
        "target_peer": LOCAL_PEER_NAME,
        "files_changed": files_changed,
        "analysis_window": analysis_window,
        "anomaly_pattern": anomaly_pattern,
        "patch_diff": diff_text,
        "codex_mode": CODEX_MODE,
        "target_daemon": target_daemon,
        "requires_confirmation": requires_confirmation,
    }
    pulse_bus.publish(
        {
            "timestamp": _iso_timestamp(),
            "source_daemon": "CodexDaemon",
            "event_type": "predictive_suggestion",
            "priority": "info",
            "source_peer": LOCAL_PEER_NAME,
            "payload": dict(update_payload),
        }
    )

    if requires_confirmation:
        manager = _PredictiveRepairManager()
        manager._append_restriction_notice(diff_path, "manual confirmation required")
        metadata = manager._create_veil_metadata(
            patch_id,
            diff_path,
            files_changed,
            scope="federated",
            analysis_window=analysis_window,
            anomaly_pattern=anomaly_pattern,
            target_daemon=target_daemon,
            source_peer=source_peer,
            target_peer=LOCAL_PEER_NAME,
        )
        manager._publish_veil_request(metadata, ledger_queue)
        return

    if FEDERATED_AUTO_APPLY and files_changed:
        applied = bool(apply_patch(diff_text))
        verification = False
        if applied:
            queue = ledger_queue if ledger_queue is not None else Queue()
            verification = bool(run_ci(queue))
        status = "applied" if applied and verification else "failed"
        applied_entry: dict[str, Any] = {
            "ts": _ledger_timestamp(),
            "event": "federated_predictive_event",
            "status": status,
            "patch_id": patch_id,
            "files_changed": files_changed,
            "analysis_window": analysis_window,
            "anomaly_pattern": anomaly_pattern,
            "source_peer": source_peer,
            "target_peer": LOCAL_PEER_NAME,
            "target_daemon": target_daemon,
            "verification_result": verification if applied else False,
        }
        log_activity(dict(applied_entry))
        if ledger_queue is not None:
            ledger_queue.put(dict(applied_entry))
        update_payload["status"] = status
        update_payload["verification_result"] = applied_entry.get("verification_result", False)
        pulse_bus.publish(
            {
                "timestamp": _iso_timestamp(),
                "source_daemon": "CodexDaemon",
                "event_type": "predictive_suggestion",
                "priority": "info",
                "source_peer": LOCAL_PEER_NAME,
                "payload": dict(update_payload),
            }
        )
        if applied and verification:
            record_self_predict_applied(files_changed, ledger_queue)


def _resolve_metadata_path(patch_id: str) -> Path:
    return CODEX_SUGGEST_DIR / f"{patch_id}.veil.json"


def _resolve_patch_file(patch_id: str, metadata: Mapping[str, object]) -> Path:
    patch_path = metadata.get("patch_path")
    if isinstance(patch_path, str) and patch_path:
        candidate = Path(patch_path)
        if not candidate.exists():
            candidate = CODEX_SUGGEST_DIR / candidate.name
        return candidate
    return CODEX_SUGGEST_DIR / f"{patch_id}.diff"


def confirm_veil_patch(patch_id: str) -> dict[str, object]:
    metadata_path = _resolve_metadata_path(patch_id)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    status = str(metadata.get("status", "pending"))
    if status not in {"pending", "suggested"}:
        raise RuntimeError("veil patch already resolved")
    diff_path = _resolve_patch_file(patch_id, metadata)
    response_format = str(metadata.get("response_format", "diff"))
    if response_format == "json_mapping":
        mapping = json.loads(diff_path.read_text(encoding="utf-8"))
        files_changed = _apply_file_mapping(mapping)
        applied = True
    else:
        diff_text = diff_path.read_text(encoding="utf-8")
        applied = bool(apply_patch(diff_text))
        files_changed = [
            str(item)
            for item in metadata.get("files_changed", [])
            if isinstance(item, str)
        ]
    if not applied:
        raise RuntimeError("patch_apply_failed")
    queue: Queue = Queue()
    verification = bool(run_ci(queue))
    if not verification:
        raise RuntimeError("verification_failed")
    metadata["status"] = "confirmed"
    metadata["confirmed_at"] = _iso_timestamp()
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    entry = {
        "ts": _ledger_timestamp(),
        "event": "veil_confirmed",
        "patch_id": patch_id,
        "files_changed": files_changed,
        "verification_result": verification,
    }
    log_activity(dict(entry))
    pulse_bus.publish(
        {
            "timestamp": _iso_timestamp(),
            "source_daemon": "CodexDaemon",
            "event_type": "veil_confirmed",
            "priority": "info",
            "payload": {
                "patch_id": patch_id,
                "status": "confirmed",
                "files_changed": files_changed,
            },
        }
    )
    record_veil_confirmed(files_changed, None)
    return metadata


def reject_veil_patch(patch_id: str) -> dict[str, object]:
    metadata_path = _resolve_metadata_path(patch_id)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    status = str(metadata.get("status", "pending"))
    if status not in {"pending", "suggested"}:
        raise RuntimeError("veil patch already resolved")
    diff_path = _resolve_patch_file(patch_id, metadata)
    if diff_path.exists():
        diff_path.unlink()
    metadata["status"] = "rejected"
    metadata["rejected_at"] = _iso_timestamp()
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    files_changed = [str(item) for item in metadata.get("files_changed", []) if isinstance(item, str)]
    entry = {
        "ts": _ledger_timestamp(),
        "event": "veil_rejected",
        "patch_id": patch_id,
        "files_changed": files_changed,
    }
    log_activity(dict(entry))
    pulse_bus.publish(
        {
            "timestamp": _iso_timestamp(),
            "source_daemon": "CodexDaemon",
            "event_type": "veil_rejected",
            "priority": "info",
            "payload": {
                "patch_id": patch_id,
                "status": "rejected",
                "files_changed": files_changed,
            },
        }
    )
    return metadata


def record_self_predict_applied(
    files_changed: Sequence[str], ledger_queue: Queue | None = None
) -> None:
    _reconcile_manifest(files_changed, ledger_queue, source_event="self_predict_applied")


def record_veil_confirmed(
    files_changed: Sequence[str], ledger_queue: Queue | None = None
) -> None:
    _reconcile_manifest(files_changed, ledger_queue, source_event="veil_confirmed")


def run_once(ledger_queue: Queue) -> dict | None:
    """Execute a single Codex self-repair cycle with multi-iteration and workspace hygiene."""

    if CODEX_MODE == "expand":
        expand_entry = _process_expand_requests(ledger_queue)
        if expand_entry is not None:
            return expand_entry

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

    max_iterations = max(1, CODEX_MAX_ITERATIONS)
    current_summary = summary
    cumulative_files: set[str] = set()
    last_entry: dict | None = None

    for iteration in range(1, max_iterations + 1):
        failing_tests = parse_failing_tests(current_summary)
        prompt = (
            "Fix the following issues in SentientOS based on pytest output:\n"
            f"{current_summary}\n"
            "Output a unified diff."
        )
        proc = subprocess.run(["codex", "exec", prompt], capture_output=True, text=True)
        diff_output = proc.stdout

        CODEX_SUGGEST_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        patch_suffix = f"{timestamp}_iter{iteration:02d}"
        patch_path = CODEX_SUGGEST_DIR / f"patch_{patch_suffix}.diff"
        patch_path.write_text(diff_output, encoding="utf-8")

        CODEX_REASONING_DIR.mkdir(parents=True, exist_ok=True)
        trace_path = CODEX_REASONING_DIR / f"trace_{patch_suffix}.json"
        trace_path.write_text(
            json.dumps(
                {
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "prompt": prompt,
                    "response": diff_output,
                    "tests_failed": failing_tests,
                    "iteration": iteration,
                    "summary": current_summary,
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
            "iterations": iteration,
            "iteration": iteration,
            "outcome": "suggested" if confirmed and files_changed else "halted",
            "target": CODEX_FOCUS,
            "verified": False,
            "reasoning_trace": trace_path.as_posix().lstrip("/"),
            "summary": current_summary,
        }
        log_activity({**suggestion_entry, "prompt": prompt})
        ledger_queue.put(suggestion_entry)
        last_entry = suggestion_entry

        if not confirmed or not files_changed:
            suggestion_entry["final_iteration"] = True
            suggestion_entry["max_iterations_reached"] = iteration >= max_iterations
            return suggestion_entry

        # Apply patch with hygiene
        patch_label = patch_path.stem
        patch_result = _call_apply_patch(diff_output, label=patch_label)
        archived_diff = patch_result.get("archived_diff")
        restored_repo = patch_result.get("restored_repo")
        failure_reason = patch_result.get("failure_reason")

        if not patch_result["applied"]:
            fail_entry = {
                **suggestion_entry,
                "event": "self_repair_failed",
                "reason": failure_reason or "patch_apply_failed",
                "failure_reason": failure_reason or "patch_apply_failed",
                "outcome": "fail",
                "restored_repo": bool(restored_repo),
                "archived_diff": archived_diff,
                "final_iteration": True,
                "iterations": iteration,
            }
            log_activity(fail_entry)
            ledger_queue.put(fail_entry)
            return fail_entry

        cumulative_files.update(files_changed)
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
                "files_changed": sorted(cumulative_files),
                "iterations": iteration,
                "final_iteration": True,
                "summary": new_summary,
                "tests_failed": [],
            }
            log_activity(success_entry)
            ledger_queue.put(success_entry)
            send_notifications(success_entry)
            _reconcile_manifest(
                success_entry["files_changed"],
                ledger_queue,
                source_event="self_repair",
            )
            return success_entry

        # Tests still failing → record failure, loop if more iterations allowed
        new_failing_tests = parse_failing_tests(new_summary)
        fail_entry = {
            **suggestion_entry,
            "event": "self_repair_failed",
            "reason": new_summary,
            "failure_reason": "ci_failed",
            "outcome": "fail",
            "tests_failed": new_failing_tests,
            "files_changed": sorted(cumulative_files),
            "iterations": iteration,
            "final_iteration": iteration == max_iterations,
            "max_iterations_reached": iteration >= max_iterations,
            "summary": new_summary,
        }
        log_activity(fail_entry)
        ledger_queue.put(fail_entry)
        last_entry = fail_entry

        if iteration >= max_iterations:
            return fail_entry

        current_summary = new_summary

    return last_entry
