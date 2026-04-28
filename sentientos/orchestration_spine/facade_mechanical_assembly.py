from __future__ import annotations

"""Mechanical-only façade assembly helpers extracted from orchestration_intent_fabric.

These helpers are intentionally narrow and non-authoritative:
- no schema-envelope shaping
- no authority decisions
- no ledger append behavior
"""

from typing import Any, Mapping


def handoff_evidence_pointers(delegated_judgment: Mapping[str, Any]) -> list[str]:
    """Build compact, deduplicated artifact pointers while preserving insertion order."""

    delegated_basis = delegated_judgment.get("basis")
    delegated_basis_map = delegated_basis if isinstance(delegated_basis, Mapping) else {}
    pointers = [
        "glow/orchestration/orchestration_next_move_proposals.jsonl",
        "glow/orchestration/orchestration_handoffs.jsonl",
        "glow/orchestration/orchestration_intents.jsonl",
    ]
    artifacts = delegated_basis_map.get("artifacts_read")
    if isinstance(artifacts, Mapping):
        for value in artifacts.values():
            if isinstance(value, str) and value:
                pointers.append(value)

    seen: set[str] = set()
    ordered: list[str] = []
    for pointer in pointers:
        if pointer not in seen:
            ordered.append(pointer)
            seen.add(pointer)
    return ordered


def normalized_compact_string_refs(values: list[str] | None) -> list[str]:
    """Normalize optional free-form refs into compact, non-empty string rows."""

    return [
        value.strip()
        for value in (values or [])
        if isinstance(value, str) and value.strip()
    ]
