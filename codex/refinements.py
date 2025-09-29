"""Adaptive refinement engine for Codex implementations."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import json

from .implementations import (
    ImplementationBlock,
    ImplementationRecord,
    Implementor,
)


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


RefinementTransform = Callable[[ImplementationBlock], ImplementationBlock | str]


class Refiner:
    """Iteratively improve Codex implementations based on feedback."""

    def __init__(
        self,
        *,
        repo_root: Path | str = Path("."),
        integration_root: Path | str | None = None,
        implementor: Implementor | None = None,
        now: Callable[[], datetime] = _default_now,
    ) -> None:
        self._repo_root = Path(repo_root)
        self._integration_root = (
            Path(integration_root)
            if integration_root is not None
            else self._repo_root / "integration"
        )
        self._integration_root.mkdir(parents=True, exist_ok=True)
        self._log_path = self._integration_root / "refinement_log.jsonl"
        self._now = now
        self._implementor = implementor or Implementor(
            repo_root=self._repo_root,
            integration_root=self._integration_root,
            now=now,
        )

    # ------------------------------------------------------------------
    # Public API
    def refine(
        self,
        spec_id: str,
        *,
        failure: str,
        change_summary: str,
        operator: str | None = None,
        transform: RefinementTransform | None = None,
        confidence_delta: str | None = "-0.1",
    ) -> ImplementationRecord:
        """Produce a refined implementation version after a failure."""

        record = self._implementor.load_record(spec_id)
        if record.final_rejected:
            raise RuntimeError(
                "Implementation marked as final rejected; further refinements halted."
            )

        parent_version = (
            record.pending_version
            or record.active_version
            or record.version_id
            or self._latest_version_id(record)
        )
        if not parent_version:
            raise ValueError("No baseline implementation available for refinement")

        parent_record = self._implementor.load_version(spec_id, parent_version)
        version_id = self._next_version_id(record)
        timestamp = self._now().isoformat()

        new_blocks = [
            self._build_refined_block(
                block,
                timestamp=timestamp,
                failure=failure,
                parent_version=parent_version,
                operator=operator,
                transform=transform,
                confidence_delta=confidence_delta,
            )
            for block in parent_record.blocks
        ]

        history_entry = {
            "timestamp": timestamp,
            "action": "refined",
            "failure": failure,
            "operator": operator,
            "version_id": version_id,
            "parent_version": parent_version,
            "change_summary": change_summary,
            "confidence_delta": confidence_delta,
        }

        version_record = ImplementationRecord(
            spec_id=spec_id,
            title=record.title,
            status="pending_review",
            generated_at=timestamp,
            blocks=new_blocks,
            ledger_entry=record.ledger_entry,
            history=list(parent_record.history or []) + [history_entry],
            version_id=version_id,
            parent_id=parent_version,
            change_summary=change_summary,
            confidence_delta=confidence_delta,
        )
        self._implementor.save_version(spec_id, version_record)

        summary = self._implementor.version_summary(
            spec_id,
            version_id,
            parent_id=parent_version,
            change_summary=change_summary,
            confidence_delta=confidence_delta,
            status="pending_review",
            timestamp=timestamp,
        )

        record.status = "pending_review"
        record.pending_version = version_id
        record.version_id = version_id
        record.parent_id = parent_version
        record.change_summary = change_summary
        record.confidence_delta = confidence_delta
        record.blocks = [replace(block, history=list(block.history)) for block in new_blocks]
        record.history = list(record.history or []) + [history_entry]
        record.versions = list(record.versions or []) + [summary]
        if parent_version and parent_version != record.active_version:
            self._implementor.update_version_entry(
                record, parent_version, status="superseded"
            )
        record.final_rejected = False
        self._implementor.save_record(record)

        self._append_log(
            "refined",
            spec_id,
            operator=operator,
            metadata={
                "failure": failure,
                "version_id": version_id,
                "parent_version": parent_version,
                "change_summary": change_summary,
                "confidence_delta": confidence_delta,
            },
        )
        return version_record

    def rollback(
        self,
        spec_id: str,
        version_id: str,
        *,
        operator: str,
        reason: str | None = None,
    ) -> ImplementationRecord:
        """Restore a previously generated implementation version."""

        record = self._implementor.load_record(spec_id)
        version_record = self._implementor.load_version(spec_id, version_id)
        timestamp = self._now().isoformat()

        rollback_entry = {
            "timestamp": timestamp,
            "action": "rollback",
            "operator": operator,
            "version_id": version_id,
            "reason": reason,
        }

        if version_record.status != "approved":
            version_record.status = "approved"
            if not version_record.approved_at:
                version_record.approved_at = timestamp
            if not version_record.approved_by:
                version_record.approved_by = operator
        version_record.history = list(version_record.history or []) + [rollback_entry]
        self._implementor.save_version(spec_id, version_record)

        record.status = "approved"
        record.pending_version = None
        record.active_version = version_id
        record.version_id = version_id
        record.history = list(record.history or []) + [rollback_entry]
        record.blocks = [
            replace(block, history=list(block.history)) for block in version_record.blocks
        ]
        record.parent_id = version_record.parent_id
        record.change_summary = version_record.change_summary
        record.confidence_delta = version_record.confidence_delta
        record.approved_at = timestamp
        record.approved_by = operator
        self._implementor.update_version_entry(
            record,
            version_id,
            status="approved",
            rolled_back_at=timestamp,
            operator=operator,
        )
        for entry in record.versions or []:
            if entry.get("version_id") != version_id and entry.get("status") == "approved":
                entry["status"] = "rolled_back"
        record.final_rejected = False
        self._implementor.save_record(record)

        self._append_log(
            "rolled_back",
            spec_id,
            operator=operator,
            metadata={
                "version_id": version_id,
                "reason": reason,
            },
        )
        return version_record

    def lock_line(
        self,
        spec_id: str,
        version_id: str,
        line_number: int,
        *,
        operator: str,
        reason: str,
    ) -> Mapping[str, Any]:
        """Record a locked line to prevent future regressions."""

        record = self._implementor.load_record(spec_id)
        entry = {
            "timestamp": self._now().isoformat(),
            "version_id": version_id,
            "line": int(line_number),
            "operator": operator,
            "reason": reason,
        }
        record.locked_lines = list(record.locked_lines or []) + [entry]
        self._implementor.save_record(record)
        self._append_log("locked_line", spec_id, operator=operator, metadata=entry)
        return entry

    def flag_final_rejected(
        self,
        spec_id: str,
        version_id: str,
        *,
        operator: str,
        reason: str,
    ) -> ImplementationRecord:
        """Mark a version as irrecoverable to halt further refinements."""

        record = self._implementor.load_record(spec_id)
        timestamp = self._now().isoformat()
        entry = {
            "timestamp": timestamp,
            "action": "final_rejected",
            "version_id": version_id,
            "operator": operator,
            "reason": reason,
        }
        record.final_rejected = True
        record.status = "rejected"
        record.pending_version = None
        if record.active_version == version_id:
            record.active_version = None
        record.history = list(record.history or []) + [entry]
        self._implementor.update_version_entry(
            record,
            version_id,
            status="final_rejected",
            operator=operator,
            reason=reason,
            final_rejected_at=timestamp,
        )
        self._implementor.save_record(record)
        self._append_log("final_rejected", spec_id, operator=operator, metadata=entry)
        return record

    # ------------------------------------------------------------------
    # Internal helpers
    def _append_log(
        self,
        action: str,
        spec_id: str,
        *,
        operator: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "timestamp": self._now().isoformat(),
            "spec_id": spec_id,
            "action": action,
        }
        if operator:
            payload["operator"] = operator
        if metadata:
            payload["metadata"] = dict(metadata)
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def _next_version_id(self, record: ImplementationRecord) -> str:
        index = 0
        for entry in record.versions or []:
            value = self._parse_version_index(entry.get("version_id"))
            if value is not None and value > index:
                index = value
        return f"v{index + 1}"

    def _latest_version_id(self, record: ImplementationRecord) -> str | None:
        versions = list(record.versions or [])
        if versions:
            last = versions[-1].get("version_id")
            if isinstance(last, str):
                return last
        return None

    def _parse_version_index(self, version_id: Any) -> int | None:
        if not isinstance(version_id, str):
            return None
        if version_id.startswith("v"):
            try:
                return int(version_id[1:])
            except ValueError:
                return None
        return None

    def _build_refined_block(
        self,
        block: ImplementationBlock,
        *,
        timestamp: str,
        failure: str,
        parent_version: str,
        operator: str | None,
        transform: RefinementTransform | None,
        confidence_delta: str | None,
    ) -> ImplementationBlock:
        updated = block
        if transform:
            result = transform(block)
            if isinstance(result, ImplementationBlock):
                updated = result
            else:
                updated = replace(block, draft=str(result))
        history = list(updated.history)
        history.append(
            {
                "timestamp": timestamp,
                "action": "refined",
                "failure": failure,
                "parent_version": parent_version,
                "operator": operator,
            }
        )
        return ImplementationBlock(
            block_id=updated.block_id,
            component=updated.component,
            target_path=updated.target_path,
            function_name=updated.function_name,
            directive=updated.directive,
            confidence=self._adjust_confidence(updated.confidence, confidence_delta),
            rollback_path=updated.rollback_path,
            draft=updated.draft,
            status="pending_review",
            created_at=timestamp,
            history=history,
            pattern_key=updated.pattern_key,
        )

    def _adjust_confidence(
        self, value: str, confidence_delta: str | None
    ) -> str:
        levels = ["low", "medium", "high"]
        if value not in levels or not confidence_delta:
            return value
        index = levels.index(value)
        if str(confidence_delta).startswith("-"):
            index = max(0, index - 1)
        elif str(confidence_delta).startswith("+"):
            index = min(len(levels) - 1, index + 1)
        return levels[index]


__all__ = ["Refiner", "RefinementTransform"]
