from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .base import AdapterActionResult, AdapterActionSpec, AdapterMetadata, AdapterRollbackResult
from .runtime import AdapterExecutionError


@dataclass(frozen=True)
class FilesystemAdapter:
    base_path: Path = Path(".")

    metadata = AdapterMetadata(
        adapter_id="filesystem",
        capabilities=("read", "write"),
        scope="explicit resources only (scoped base path)",
        external_effects="yes",
        reversibility="bounded",
        requires_privilege=True,
        allow_epr=False,
    )

    action_specs = {
        "read": AdapterActionSpec(
            action="read",
            capability="read",
            authority_impact="none",
            external_effects="no",
            reversibility="none",
            requires_privilege=False,
        ),
        "write": AdapterActionSpec(
            action="write",
            capability="write",
            authority_impact="local",
            external_effects="yes",
            reversibility="bounded",
            requires_privilege=True,
        ),
    }

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_path", Path(self.base_path))

    def probe(self) -> bool:
        return self.base_path.exists() and self.base_path.is_dir()

    def describe(self) -> AdapterMetadata:
        return self.metadata

    def execute(
        self,
        action: str,
        params: Mapping[str, object],
        context,
    ) -> AdapterActionResult:
        if action == "read":
            return self._read(params)
        if action == "write":
            return self._write(params)
        raise AdapterExecutionError(f"unsupported filesystem action: {action}")

    def rollback(self, ref: Mapping[str, object], context) -> AdapterRollbackResult:
        action = str(ref.get("action", ""))
        if action != "write":
            raise AdapterExecutionError("filesystem adapter only supports write rollback")
        target = self._resolve_path(ref)
        existed = bool(ref.get("existed"))
        if existed:
            content = ref.get("previous_content")
            if not isinstance(content, str):
                raise AdapterExecutionError("rollback ref missing previous_content")
            target.write_text(content, encoding="utf-8")
        else:
            if target.exists():
                target.unlink()
        return AdapterRollbackResult(
            action="write",
            success=True,
            detail={"path": str(target), "restored": existed},
        )

    def _read(self, params: Mapping[str, object]) -> AdapterActionResult:
        target = self._resolve_path(params)
        content = target.read_text(encoding="utf-8")
        return AdapterActionResult(
            action="read",
            outcome={"path": str(target), "content": content},
            rollback_ref=None,
        )

    def _write(self, params: Mapping[str, object]) -> AdapterActionResult:
        target = self._resolve_path(params)
        content = params.get("content")
        if not isinstance(content, str):
            raise AdapterExecutionError("filesystem write requires string content")
        existed = target.exists()
        previous = target.read_text(encoding="utf-8") if existed else None
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        rollback_ref = {
            "action": "write",
            "path": str(target),
            "existed": existed,
            "previous_content": previous,
        }
        return AdapterActionResult(
            action="write",
            outcome={"path": str(target), "bytes_written": len(content)},
            rollback_ref=rollback_ref,
        )

    def _resolve_path(self, params: Mapping[str, object]) -> Path:
        raw_path = params.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            raise AdapterExecutionError("filesystem action requires path")
        target = (self.base_path / raw_path).resolve()
        base = self.base_path.resolve()
        if base not in target.parents and target != base:
            raise AdapterExecutionError("filesystem path escapes adapter scope")
        return target


__all__ = ["FilesystemAdapter"]
