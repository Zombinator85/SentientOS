"""Dashboard helpers for Codex implementation drafts."""
from __future__ import annotations

from typing import Any, Mapping

from codex.implementations import Implementor

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


__all__ = ["implementations_panel_state", "PANEL_TITLE"]

