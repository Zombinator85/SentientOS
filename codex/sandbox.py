"""Internal sandboxing utilities for Codex workflows."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import shutil
import shlex
import subprocess
import uuid
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

import difflib


class SandboxViolation(PermissionError):
    """Raised when a Codex operation attempts to escape the sandbox."""


@dataclass(frozen=True)
class StagedRecord:
    """Metadata for a staged mutation before operator approval."""

    stage_id: str
    target_path: str
    diff: str
    approved: bool
    staged_path: Path


class CodexSandbox:
    """Enforce filesystem, execution, and mutation boundaries for Codex."""

    _DEFAULT_ALLOWED_PATHS = (
        "integration",
        "tests/generated",
        "glow",
        ".codex_sandbox",
    )
    _ALLOWED_COMMANDS = frozenset({"pytest", "python", "python3"})
    _BLOCKED_COMMANDS = frozenset(
        {
            "pip",
            "pip3",
            "apt",
            "apt-get",
            "curl",
            "wget",
            "npm",
            "yarn",
            "pnpm",
            "brew",
        }
    )

    def __init__(
        self,
        root: Path | str = Path("."),
        *,
        allowed_paths: Iterable[Path | str] | None = None,
        allowed_commands: Iterable[str] | None = None,
        allowed_scripts: Iterable[Path | str] | None = None,
    ) -> None:
        self._root = Path(root).resolve()
        self._sandbox_root = self._root / ".codex_sandbox"
        self._sandbox_root.mkdir(parents=True, exist_ok=True)
        self._staging_dir = self._sandbox_root / "staging"
        self._staging_dir.mkdir(parents=True, exist_ok=True)
        self._allowed_paths = (
            [self._resolve_path(path) for path in allowed_paths]
            if allowed_paths
            else [self._resolve_path(path) for path in self._DEFAULT_ALLOWED_PATHS]
        )
        self._allowed_commands = set(allowed_commands or self._ALLOWED_COMMANDS)
        self._allowed_scripts = {self._resolve_path(path) for path in allowed_scripts or []}

    # ------------------------------------------------------------------
    # Filesystem boundaries
    def reset(self) -> None:
        """Clear staged state while keeping sandbox folders available."""

        shutil.rmtree(self._staging_dir, ignore_errors=True)
        self._staging_dir.mkdir(parents=True, exist_ok=True)

    def commit_text(
        self,
        path: Path | str,
        content: str,
        *,
        approved: bool,
        metadata: Mapping[str, Any] | None = None,
    ) -> StagedRecord:
        """Stage a textual mutation and optionally apply when approved."""

        record = self.stage_mutation(path, content, metadata=metadata)
        if approved:
            self.apply_staged(record.stage_id, operator=(metadata or {}).get("operator"))
        return record

    def commit_json(
        self,
        path: Path | str,
        payload: Mapping[str, Any],
        *,
        approved: bool,
        metadata: Mapping[str, Any] | None = None,
    ) -> StagedRecord:
        """Serialize payload to JSON, stage it, and apply on approval."""

        content = json.dumps(payload, sort_keys=True, indent=2)
        metadata = self._merge_metadata(metadata, {"format": "json"})
        return self.commit_text(path, content, approved=approved, metadata=metadata)

    def append_jsonl(
        self,
        path: Path | str,
        payload: Mapping[str, Any],
        *,
        approved: bool,
        metadata: Mapping[str, Any] | None = None,
    ) -> StagedRecord:
        """Append a JSONL record via staged mutation."""

        resolved = self._require_writable(path)
        existing = resolved.read_text(encoding="utf-8") if resolved.exists() else ""
        line = json.dumps(dict(payload), sort_keys=True)
        separator = "" if not existing or existing.endswith("\n") else "\n"
        new_content = f"{existing}{separator}{line}\n"
        metadata = self._merge_metadata(metadata, {"format": "jsonl"})
        return self.commit_text(resolved, new_content, approved=approved, metadata=metadata)

    def stage_mutation(
        self,
        path: Path | str,
        proposed_content: str,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> StagedRecord:
        """Record a pending mutation without applying it."""

        resolved = self._require_writable(path)
        original = resolved.read_text(encoding="utf-8") if resolved.exists() else ""
        diff = "\n".join(
            difflib.unified_diff(
                original.splitlines(),
                proposed_content.splitlines(),
                fromfile=str(resolved),
                tofile=str(resolved),
                lineterm="",
            )
        )
        stage_id = f"stage-{uuid.uuid4().hex}"
        metadata_payload: MutableMapping[str, Any] = {
            "stage_id": stage_id,
            "target_path": str(resolved),
            "diff": diff,
            "approved": False,
            "proposed_content": proposed_content,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if metadata:
            metadata_payload["metadata"] = dict(metadata)
        stage_path = self._staging_dir / f"{stage_id}.json"
        stage_path.write_text(
            json.dumps(metadata_payload, sort_keys=True, indent=2), encoding="utf-8"
        )
        return StagedRecord(
            stage_id=stage_id,
            target_path=str(resolved),
            diff=diff,
            approved=False,
            staged_path=stage_path,
        )

    def apply_staged(self, stage_id: str, *, operator: str | None = None) -> Path:
        """Apply a staged mutation once an operator approves it."""

        stage_path = self._staging_dir / f"{stage_id}.json"
        if not stage_path.exists():
            raise FileNotFoundError(f"Missing staged mutation {stage_id}")
        data = json.loads(stage_path.read_text(encoding="utf-8"))
        resolved = self._require_writable(Path(data["target_path"]))
        if data.get("approved"):
            return resolved
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(str(data.get("proposed_content", "")), encoding="utf-8")
        data["approved"] = True
        data["approved_by"] = operator
        data["applied_at"] = datetime.now(timezone.utc).isoformat()
        stage_path.write_text(json.dumps(data, sort_keys=True, indent=2), encoding="utf-8")
        return resolved

    # ------------------------------------------------------------------
    # Command execution
    def run_command(
        self,
        command: Sequence[str] | str,
        *,
        runner: Any | None = None,
    ) -> Any:
        """Execute an allowlisted command or raise when forbidden."""

        tokens = self._normalize_command(command)
        if not tokens:
            raise SandboxViolation("Empty command is not permitted")

        binary = tokens[0]
        if binary in self._BLOCKED_COMMANDS:
            raise SandboxViolation(f"Command {binary} is explicitly blocked")
        if binary not in self._allowed_commands:
            raise SandboxViolation(f"Command {binary} is not allowlisted for Codex")

        if binary in {"python", "python3"}:
            self._validate_python_command(tokens)

        if runner is None:
            runner = subprocess.run
            return runner(tokens, check=False, capture_output=True, text=True)
        return runner(tokens)

    # ------------------------------------------------------------------
    # Observability helpers
    def boundaries(self) -> Mapping[str, list[str]]:
        """Summarize sandbox allowlists for reporting."""

        return {
            "paths": [str(path) for path in sorted(self._allowed_paths)],
            "commands": sorted(self._allowed_commands),
            "blocked_commands": sorted(self._BLOCKED_COMMANDS),
            "allowed_scripts": [str(path) for path in sorted(self._allowed_scripts)],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    def _resolve_path(self, path: Path | str) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = (self._root / candidate).resolve()
        else:
            candidate = candidate.resolve()
        return candidate

    def _require_writable(self, path: Path | str) -> Path:
        resolved = self._resolve_path(path)
        for allowed in self._allowed_paths:
            if resolved == allowed or allowed in resolved.parents:
                return resolved
        raise SandboxViolation(f"Write attempt outside Codex sandbox: {resolved}")

    def _normalize_command(self, command: Sequence[str] | str) -> list[str]:
        if isinstance(command, str):
            return shlex.split(command)
        return list(command)

    def _validate_python_command(self, tokens: Sequence[str]) -> None:
        script = None
        if "-m" in tokens:
            index = tokens.index("-m")
            script = tokens[index + 1] if len(tokens) > index + 1 else None
            if script != "pytest":
                raise SandboxViolation("Only `python -m pytest` is allowed for modules")
            return

        for token in tokens[1:]:
            if not token.startswith("-"):
                script = token
                break

        if script is None:
            raise SandboxViolation("Python execution requires an explicit script")

        resolved_script = self._resolve_path(script)
        if self._allowed_scripts and resolved_script not in self._allowed_scripts:
            raise SandboxViolation(f"Script {resolved_script} is not allowlisted")

    def _merge_metadata(
        self, metadata: Mapping[str, Any] | None, extra: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        payload: MutableMapping[str, Any] = dict(metadata or {})
        for key, value in extra.items():
            payload.setdefault(key, value)
        return payload


__all__ = ["CodexSandbox", "SandboxViolation", "StagedRecord"]
