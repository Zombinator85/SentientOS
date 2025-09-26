"""Codex rewrite helpers for bounded, ledger-gated evolution."""
from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, MutableMapping, Optional

import difflib


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RewritePatch:
    """Representation of a reversible Codex patch."""

    patch_id: str
    daemon: str
    target_path: str
    timestamp: datetime
    diff: str
    original_content: str
    modified_content: str
    reason: str
    confidence: float
    urgency: str
    source: str = "codex"
    status: str = "pending"
    override: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.isoformat()
        return payload

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "RewritePatch":
        payload = dict(payload)
        payload["timestamp"] = datetime.fromisoformat(payload["timestamp"])
        return cls(**payload)

    def diff_summary(self, max_lines: int = 6) -> str:
        lines = self.diff.splitlines()
        if len(lines) <= max_lines:
            return "\n".join(lines)
        head = lines[: max_lines - 1]
        head.append("…")
        return "\n".join(head)


class LedgerInterface:
    """Protocol-like interface for Codex ledger verification."""

    def verify_patch(self, patch: RewritePatch) -> bool:  # pragma: no cover - interface only
        raise NotImplementedError


class PatchStorage:
    """Persist Codex rewrite patches and maintain glow + quarantine directories."""

    def __init__(
        self,
        base_dir: Path | str = Path("glow/patches"),
        quarantine_dir: Path | str = Path("daemon/quarantine"),
    ) -> None:
        self.base_dir = Path(base_dir)
        self.quarantine_dir = Path(quarantine_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)

    def save_patch(self, patch: RewritePatch) -> Path:
        patch_dir = self._patch_dir(patch.patch_id)
        patch_dir.mkdir(parents=True, exist_ok=True)
        self._write_contents(patch_dir, patch)
        return patch_dir

    def update_patch(self, patch: RewritePatch) -> None:
        patch_dir = self._locate_patch_dir(patch.patch_id)
        if patch_dir is None:
            raise FileNotFoundError(f"Missing patch directory for {patch.patch_id}")
        self._write_metadata(patch_dir, patch)

    def iter_patches(self) -> Iterable[RewritePatch]:
        yield from self._iter_from_dir(self.base_dir)
        yield from self._iter_from_dir(self.quarantine_dir)

    def load_patch(self, patch_id: str) -> RewritePatch:
        patch_dir = self._locate_patch_dir(patch_id)
        if patch_dir is None:
            raise FileNotFoundError(f"Patch {patch_id} not found")
        metadata = json.loads((patch_dir / "patch.json").read_text(encoding="utf-8"))
        patch = RewritePatch.from_dict(metadata)
        patch.original_content = (patch_dir / "original.txt").read_text(encoding="utf-8")
        patch.modified_content = (patch_dir / "modified.txt").read_text(encoding="utf-8")
        return patch

    def quarantine(self, patch: RewritePatch) -> Path:
        patch.status = "quarantined"
        temp_dir = self._patch_dir(patch.patch_id)
        target_dir = self.quarantine_dir / patch.patch_id
        if temp_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
            shutil.move(str(temp_dir), target_dir)
        self._write_metadata(target_dir, patch)
        return target_dir

    def _patch_dir(self, patch_id: str) -> Path:
        return self.base_dir / patch_id

    def _locate_patch_dir(self, patch_id: str) -> Optional[Path]:
        candidates = [self.base_dir / patch_id, self.quarantine_dir / patch_id]
        for directory in candidates:
            if directory.exists():
                return directory
        return None

    def _write_contents(self, patch_dir: Path, patch: RewritePatch) -> None:
        self._write_metadata(patch_dir, patch)
        (patch_dir / "original.txt").write_text(patch.original_content, encoding="utf-8")
        (patch_dir / "modified.txt").write_text(patch.modified_content, encoding="utf-8")

    def _write_metadata(self, patch_dir: Path, patch: RewritePatch) -> None:
        patch_dir.mkdir(parents=True, exist_ok=True)
        (patch_dir / "patch.json").write_text(
            json.dumps(patch.to_dict(), sort_keys=True, indent=2),
            encoding="utf-8",
        )

    def _iter_from_dir(self, directory: Path) -> Iterable[RewritePatch]:
        if not directory.exists():
            return
        for entry in sorted(directory.iterdir()):
            if not entry.is_dir():
                continue
            metadata_path = entry / "patch.json"
            if not metadata_path.exists():
                continue
            data = json.loads(metadata_path.read_text(encoding="utf-8"))
            patch = RewritePatch.from_dict(data)
            patch.original_content = (entry / "original.txt").read_text(encoding="utf-8")
            patch.modified_content = (entry / "modified.txt").read_text(encoding="utf-8")
            yield patch


_URGENCY_ORDER: MutableMapping[str, int] = {
    "critical": 3,
    "high": 2,
    "medium": 1,
    "low": 0,
}


@dataclass
class RewriteRequest:
    patch: RewritePatch
    created_at: datetime


class ScopedRewriteEngine:
    """Manage Codex rewrites with cooldowns, ledger gating, and patch storage."""

    def __init__(
        self,
        ledger: LedgerInterface,
        *,
        storage: PatchStorage | None = None,
        cooldown: timedelta = timedelta(minutes=30),
        now: Callable[[], datetime] = _default_now,
    ) -> None:
        self._ledger = ledger
        self._storage = storage or PatchStorage()
        self._cooldown = cooldown
        self._now = now
        self._pending: Dict[str, List[RewriteRequest]] = {}
        self._last_applied: Dict[str, datetime] = {}

    def request_rewrite(
        self,
        daemon: str,
        target_path: Path,
        new_content: str,
        *,
        reason: str,
        confidence: float,
        urgency: str,
        source: str = "codex",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RewritePatch:
        if urgency not in _URGENCY_ORDER:
            raise ValueError(f"Unsupported urgency tag: {urgency}")
        original_content = target_path.read_text(encoding="utf-8")
        diff = "\n".join(
            difflib.unified_diff(
                original_content.splitlines(),
                new_content.splitlines(),
                fromfile=str(target_path),
                tofile=str(target_path),
                lineterm="",
            )
        )
        patch_id = uuid.uuid4().hex
        patch = RewritePatch(
            patch_id=patch_id,
            daemon=daemon,
            target_path=str(target_path),
            timestamp=self._now(),
            diff=diff,
            original_content=original_content,
            modified_content=new_content,
            reason=reason,
            confidence=float(confidence),
            urgency=urgency,
            source=source,
            metadata=metadata or {},
        )
        self._storage.save_patch(patch)
        request = RewriteRequest(patch=patch, created_at=patch.timestamp)
        self._pending.setdefault(daemon, []).append(request)
        self._sort_requests(daemon)
        return patch

    def process_pending(self) -> List[RewritePatch]:
        applied: List[RewritePatch] = []
        for daemon, requests in list(self._pending.items()):
            if not requests:
                continue
            last_time = self._last_applied.get(daemon)
            if last_time is not None and self._now() - last_time < self._cooldown:
                continue
            request = requests.pop(0)
            if not requests:
                self._pending.pop(daemon, None)
            patch = request.patch
            approved = self._ledger.verify_patch(patch)
            if approved:
                self._apply_patch(patch)
                patch.status = "applied"
                self._last_applied[daemon] = self._now()
                applied.append(patch)
            else:
                self._storage.quarantine(patch)
            self._storage.update_patch(patch)
        return applied

    def revert_patch(self, patch_id: str) -> RewritePatch:
        patch = self._storage.load_patch(patch_id)
        Path(patch.target_path).write_text(patch.original_content, encoding="utf-8")
        patch.status = "reverted"
        self._storage.update_patch(patch)
        return patch

    def approve_patch(self, patch_id: str) -> RewritePatch:
        patch = self._storage.load_patch(patch_id)
        patch.status = "approved"
        self._storage.update_patch(patch)
        return patch

    def lock_patch(self, patch_id: str) -> RewritePatch:
        patch = self._storage.load_patch(patch_id)
        patch.status = "locked"
        self._storage.update_patch(patch)
        return patch

    def set_override(self, patch_id: str, enabled: bool) -> RewritePatch:
        patch = self._storage.load_patch(patch_id)
        patch.override = bool(enabled)
        self._storage.update_patch(patch)
        return patch

    def backlog(self, daemon: str) -> List[RewritePatch]:
        return [request.patch for request in self._pending.get(daemon, [])]

    def _apply_patch(self, patch: RewritePatch) -> None:
        Path(patch.target_path).write_text(patch.modified_content, encoding="utf-8")

    def _sort_requests(self, daemon: str) -> None:
        queue = self._pending[daemon]
        queue.sort(
            key=lambda request: (
                -_URGENCY_ORDER.get(request.patch.urgency, 0),
                -request.patch.confidence,
                request.created_at,
            )
        )


class RewriteDashboard:
    """Provide dashboard-friendly summaries for Codex rewrites."""

    def __init__(self, storage: PatchStorage) -> None:
        self._storage = storage

    def rows(self) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        for patch in self._storage.iter_patches():
            entries.append(
                {
                    "patch_id": patch.patch_id,
                    "daemon": patch.daemon,
                    "reason": patch.reason,
                    "status": patch.status,
                    "diff_summary": patch.diff_summary(),
                    "confidence": patch.confidence,
                    "override": patch.override,
                    "actions": {
                        "approve": patch.status == "pending",
                        "revert": patch.status in {"applied", "approved"},
                        "lock": patch.status != "locked",
                    },
                }
            )
        return entries
