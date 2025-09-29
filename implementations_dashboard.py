"""Dashboard helpers for Codex implementation drafts."""
from __future__ import annotations

import difflib
from typing import Any, Iterable, Mapping

from codex.implementations import Implementor, ImplementationRecord

PANEL_TITLE = "Implementations"


def implementations_panel_state(
    implementor: Implementor | None = None,
    *,
    include_history: bool = False,
) -> Mapping[str, Any]:
    """Return dashboard data summarizing pending Codex implementations."""

    eng = implementor or Implementor()
    records = eng.list_records()
    items: list[dict[str, Any]] = []
    for record in records:
        entry = {
            "spec_id": record.get("spec_id"),
            "title": record.get("title"),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "ledger_entry": record.get("ledger_entry"),
            "approved_at": record.get("approved_at"),
            "approved_by": record.get("approved_by"),
            "registry_path": record.get("registry_path"),
            "active_version": record.get("active_version"),
            "pending_version": record.get("pending_version"),
            "final_rejected": record.get("final_rejected", False),
        }
        blocks_payload: list[dict[str, Any]] = []
        for block in record.get("blocks", []):
            block_entry = {
                "block_id": block.get("block_id"),
                "component": block.get("component"),
                "confidence": block.get("confidence"),
                "status": block.get("status"),
                "target_path": block.get("target_path"),
                "function_name": block.get("function_name"),
                "rollback_path": block.get("rollback_path"),
                "directive": block.get("directive"),
            }
            if include_history:
                block_entry["history"] = block.get("history", [])
            blocks_payload.append(block_entry)
        entry["blocks"] = blocks_payload
        versions_payload: list[dict[str, Any]] = []
        for version in record.get("versions", []) or []:
            version_id = version.get("version_id")
            parent_id = version.get("parent_id")
            diff_text = ""
            try:
                current_version = eng.load_version(entry["spec_id"], version_id)
            except (FileNotFoundError, TypeError, ValueError):
                current_version = None
            parent_version_record: ImplementationRecord | None
            if parent_id:
                try:
                    parent_version_record = eng.load_version(entry["spec_id"], parent_id)
                except (FileNotFoundError, ValueError):
                    parent_version_record = None
            else:
                parent_version_record = None
            current_text = _blocks_to_text(
                getattr(current_version, "blocks", None)
            )
            parent_text = _blocks_to_text(
                getattr(parent_version_record, "blocks", None)
            )
            if current_text or parent_text:
                diff_lines = difflib.unified_diff(
                    parent_text.splitlines(),
                    current_text.splitlines(),
                    fromfile=parent_id or "origin",
                    tofile=version_id or "pending",
                    lineterm="",
                )
                diff_text = "\n".join(diff_lines)
            version_entry = dict(version)
            if diff_text:
                version_entry["diff"] = diff_text
            versions_payload.append(version_entry)
        if versions_payload:
            entry["versions"] = versions_payload
        if record.get("locked_lines"):
            entry["locked_lines"] = record.get("locked_lines")
        if include_history:
            entry["history"] = record.get("history", [])
        items.append(entry)

    return {
        "panel": PANEL_TITLE,
        "implementations": items,
        "pending": [item for item in items if item.get("status") == "pending_review"],
        "approved": [item for item in items if item.get("status") == "approved"],
        "rejected": [item for item in items if item.get("status") == "rejected"],
    }


def _blocks_to_text(blocks: Iterable[Any] | None) -> str:
    if not blocks:
        return ""
    contents: list[str] = []
    for block in blocks:
        if isinstance(block, Mapping):
            draft = block.get("draft", "")
        else:
            draft = getattr(block, "draft", "")
        contents.append(str(draft or ""))
    return "\n".join(contents)


__all__ = ["implementations_panel_state", "PANEL_TITLE"]

