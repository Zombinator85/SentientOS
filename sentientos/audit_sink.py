from __future__ import annotations

from dataclasses import dataclass
import json
import os
import datetime
import hashlib
from pathlib import Path
from typing import Mapping, Literal, Any, TextIO


AuditMode = Literal["baseline", "runtime", "both"]


@dataclass(frozen=True)
class AuditSinkConfig:
    baseline_path: Path
    runtime_dir: Path
    runtime_filename: str = "privileged_audit.runtime.jsonl"
    mode: AuditMode = "runtime"
    allow_baseline_write: bool = False

    @property
    def runtime_path(self) -> Path:
        return self.runtime_dir / self.runtime_filename


def _resolve_mode(raw: str | None) -> AuditMode:
    normalized = (raw or "runtime").strip().lower()
    if normalized in {"baseline", "runtime", "both"}:
        return normalized
    return "runtime"


def resolve_audit_paths(repo_root: Path, env: Mapping[str, str] | None = None) -> AuditSinkConfig:
    data = env or os.environ
    baseline_raw = data.get("SENTIENTOS_AUDIT_BASELINE_PATH", "logs/privileged_audit.jsonl")
    runtime_raw = data.get("SENTIENTOS_AUDIT_RUNTIME_DIR", "pulse/audit")
    mode = _resolve_mode(data.get("SENTIENTOS_AUDIT_MODE"))
    allow_baseline_write = data.get("SENTIENTOS_AUDIT_ALLOW_BASELINE_WRITE", "0") == "1"

    baseline_path = Path(baseline_raw)
    runtime_dir = Path(runtime_raw)
    if not baseline_path.is_absolute():
        baseline_path = repo_root / baseline_path
    if not runtime_dir.is_absolute():
        runtime_dir = repo_root / runtime_dir

    return AuditSinkConfig(
        baseline_path=baseline_path,
        runtime_dir=runtime_dir,
        runtime_filename="privileged_audit.runtime.jsonl",
        mode=mode,
        allow_baseline_write=allow_baseline_write,
    )


def _hash_entry(timestamp: str, data: object, prev_hash: str) -> str:
    digest = hashlib.sha256()
    digest.update(timestamp.encode("utf-8"))
    digest.update(json.dumps(data, sort_keys=True).encode("utf-8"))
    digest.update(prev_hash.encode("utf-8"))
    return digest.hexdigest()


def _last_rolling_hash(path: Path) -> str:
    if not path.exists():
        return "0" * 64
    previous = "0" * 64
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        if not isinstance(raw, dict):
            raise ValueError(f"audit sink found non-object row in {path}")
        timestamp = raw.get("timestamp")
        data = raw.get("data")
        found_prev = raw.get("prev_hash")
        current = raw.get("rolling_hash") or raw.get("hash")
        if not isinstance(timestamp, str) or data is None or found_prev != previous:
            raise ValueError(f"audit sink refuses to append to broken chain: {path}")
        expected = _hash_entry(timestamp, data, previous)
        if current != expected:
            raise ValueError(f"audit sink refuses to append to broken chain: {path}")
        previous = str(current)
    return previous


def _as_audit_entry(path: Path, event_dict: dict[str, Any]) -> dict[str, Any]:
    timestamp = event_dict.get("timestamp")
    data = event_dict.get("data")
    prev_hash = event_dict.get("prev_hash")
    current = event_dict.get("rolling_hash") or event_dict.get("hash")
    if isinstance(timestamp, str) and data is not None and isinstance(prev_hash, str):
        expected = _hash_entry(timestamp, data, prev_hash)
        if current == expected:
            return {"timestamp": timestamp, "data": data, "prev_hash": prev_hash, "rolling_hash": str(current)}

    previous = _last_rolling_hash(path)
    wrapped_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    wrapped_data = dict(event_dict)
    wrapped_data.pop("prev_hash", None)
    wrapped_data.pop("rolling_hash", None)
    wrapped_data.pop("hash", None)
    return {
        "timestamp": wrapped_timestamp,
        "data": wrapped_data,
        "prev_hash": previous,
        "rolling_hash": _hash_entry(wrapped_timestamp, wrapped_data, previous),
    }


def open_runtime_writer(config: AuditSinkConfig) -> TextIO:
    config.runtime_dir.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_APPEND | os.O_WRONLY
    fd = os.open(config.runtime_path, flags, 0o644)
    return os.fdopen(fd, "a", encoding="utf-8")


def _append_event(path: Path, event_dict: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(_as_audit_entry(path, event_dict), sort_keys=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(payload + "\n")


def safe_write_event(config: AuditSinkConfig, event_dict: dict[str, Any]) -> None:
    if config.mode in {"runtime", "both"}:
        _append_event(config.runtime_path, event_dict)

    if config.allow_baseline_write and config.mode in {"baseline", "both"}:
        _append_event(config.baseline_path, event_dict)
