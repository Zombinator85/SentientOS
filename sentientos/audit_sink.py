from __future__ import annotations

from dataclasses import dataclass
import json
import os
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


def open_runtime_writer(config: AuditSinkConfig) -> TextIO:
    config.runtime_dir.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_APPEND | os.O_WRONLY
    fd = os.open(config.runtime_path, flags, 0o644)
    return os.fdopen(fd, "a", encoding="utf-8")


def safe_write_event(config: AuditSinkConfig, event_dict: dict[str, Any]) -> None:
    payload = json.dumps(event_dict, sort_keys=True)
    if config.mode in {"runtime", "both"}:
        with open_runtime_writer(config) as handle:
            handle.write(payload + "\n")

    if config.allow_baseline_write and config.mode in {"baseline", "both"}:
        config.baseline_path.parent.mkdir(parents=True, exist_ok=True)
        with config.baseline_path.open("a", encoding="utf-8") as handle:
            handle.write(payload + "\n")
