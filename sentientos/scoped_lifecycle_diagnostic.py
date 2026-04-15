from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sentientos.scoped_mutation_lifecycle import SCOPED_ACTION_IDS, resolve_scoped_mutation_lifecycle
from sentientos.scoped_slice_health import synthesize_scoped_slice_health
from sentientos.scoped_slice_health_history import persist_scoped_slice_health_history
from sentientos.scoped_slice_stability import derive_scoped_slice_stability
from sentientos.scoped_slice_retrospective_integrity import derive_scoped_slice_retrospective_integrity_review
from sentientos.scoped_slice_attention_recommendation import derive_scoped_slice_attention_recommendation
from sentientos.delegated_judgment_fabric import collect_delegated_judgment_evidence, synthesize_delegated_judgment
from sentientos.orchestration_intent_fabric import (
    admit_orchestration_intent,
    append_orchestration_intent_ledger,
    build_handoff_execution_gap_map,
    executable_handoff_map,
    resolve_orchestration_result,
    synthesize_orchestration_intent,
)


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
    slice_health = synthesize_scoped_slice_health(rows)
    slice_health_history = persist_scoped_slice_health_history(root, slice_health=slice_health)
    recent_history = slice_health_history.get("recent_history") or []
    slice_stability = derive_scoped_slice_stability(recent_history)
    retrospective_integrity_review = derive_scoped_slice_retrospective_integrity_review(
        recent_history,
        slice_stability=slice_stability,
    )
    operator_attention_recommendation = derive_scoped_slice_attention_recommendation(
        slice_health=slice_health,
        slice_health_history=slice_health_history,
        slice_stability=slice_stability,
        retrospective_integrity_review=retrospective_integrity_review,
    )
    delegated_judgment_evidence = collect_delegated_judgment_evidence(
        root,
        scoped_lifecycle={
            "slice_health": slice_health,
            "slice_stability": slice_stability,
            "slice_retrospective_integrity_review": retrospective_integrity_review,
        },
    )
    delegated_judgment = synthesize_delegated_judgment(delegated_judgment_evidence)
    orchestration_intent = synthesize_orchestration_intent(delegated_judgment)
    orchestration_ledger_path = append_orchestration_intent_ledger(root, orchestration_intent)
    handoff_result = admit_orchestration_intent(root, orchestration_intent)
    orchestration_result = resolve_orchestration_result(root, handoff_result)
    return {
        "scope": "constitutional_execution_fabric_scoped_slice",
        "overall_outcome": overall,
        "slice_health": slice_health,
        "slice_health_history": slice_health_history,
        "slice_stability": slice_stability,
        "slice_retrospective_integrity_review": retrospective_integrity_review,
        "slice_operator_attention_recommendation": operator_attention_recommendation,
        "delegated_judgment": delegated_judgment,
        "orchestration_handoff": {
            "gap_map": build_handoff_execution_gap_map(root),
            "executable_handoff_map": executable_handoff_map(),
            "intent": orchestration_intent,
            "intent_ledger_path": str(orchestration_ledger_path.relative_to(root)),
            "handoff_result": handoff_result,
            "execution_result": orchestration_result,
        },
        "actions": rows,
    }
