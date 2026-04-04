from __future__ import annotations

from typing import Any


def build_authority_of_judgment(
    *,
    decision_class: str,
    authoritative_surface: str,
    advisory_surfaces: list[str],
    disagreement_present: bool,
    reconciliation_rule: str,
    authority_of_judgment: str = "bounded_class_local_authority",
    descriptive_surfaces: list[str] | None = None,
    reconciliation: dict[str, Any] | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "decision_class": decision_class,
        "authoritative_surface": authoritative_surface,
        "advisory_surfaces": list(advisory_surfaces),
        "descriptive_surfaces": list(descriptive_surfaces or []),
        "disagreement_present": disagreement_present,
        "surface_disagreement": disagreement_present,
        "reconciliation_rule": reconciliation_rule,
        "authority_of_judgment": authority_of_judgment,
        "reconciliation": dict(reconciliation or {}),
    }
    if extra_fields:
        payload.update(extra_fields)
    return payload
