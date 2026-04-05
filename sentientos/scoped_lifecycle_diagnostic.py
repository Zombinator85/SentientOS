from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sentientos.scoped_mutation_lifecycle import SCOPED_ACTION_IDS, resolve_scoped_mutation_lifecycle


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def build_scoped_lifecycle_diagnostic(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    router_rows = _read_jsonl(root / "pulse/forge_events.jsonl")
    rows: list[dict[str, Any]] = []
    for action_id in SCOPED_ACTION_IDS:
        correlation_id = ""
        for row in reversed(router_rows):
            if row.get("event") == "constitutional_mutation_router_execution" and str(row.get("typed_action_id") or "") == action_id:
                correlation_id = str(row.get("correlation_id") or "")
                break
        if correlation_id:
            rows.append(resolve_scoped_mutation_lifecycle(root, action_id=action_id, correlation_id=correlation_id))
        else:
            rows.append(
                {
                    "typed_action_identity": action_id,
                    "correlation_id": None,
                    "outcome_class": "fragmented_unresolved",
                    "findings": [{"kind": "router_event_missing", "surface": "pulse/forge_events.jsonl"}],
                }
            )

    order = {"success": 0, "denied": 1, "failed_after_admission": 2, "fragmented_unresolved": 3}
    overall = max((str(item.get("outcome_class") or "fragmented_unresolved") for item in rows), key=lambda val: order.get(val, 99))
    return {
        "scope": "constitutional_execution_fabric_scoped_slice",
        "overall_outcome": overall,
        "actions": rows,
    }
