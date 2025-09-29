"""Codex Scaffold Dashboard Panel
Auto-generated placeholder for the Scaffolds panel.
"""

from __future__ import annotations

from typing import Any, Mapping

from codex.scaffolds import ScaffoldEngine

PANEL_TITLE = "Scaffolds"


def scaffolds_panel_state(
    engine: ScaffoldEngine | None = None,
    *,
    include_history: bool = False,
) -> Mapping[str, Any]:
    """Return dashboard data summarizing generated scaffolds."""

    eng = engine or ScaffoldEngine()
    records = eng.list_scaffolds()
    items: list[dict[str, Any]] = []
    for record in records:
        item = {
            k: record.get(k)
            for k in ("spec_id", "title", "status", "paths", "generated_at", "ledger_entry")
        }
        if include_history:
            item["history"] = record.get("history", [])
        items.append(item)
    return {
        "panel": PANEL_TITLE,
        "scaffolds": items,
        "inactive": [item for item in items if item.get("status") == "inactive"],
        "enabled": [item for item in items if item.get("status") == "enabled"],
        "archived": [item for item in items if item.get("status") == "archived"],
    }
