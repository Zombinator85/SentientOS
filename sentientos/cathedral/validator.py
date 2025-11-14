"""Semantic validation for Cathedral amendments."""

from __future__ import annotations

from typing import Any, List, Mapping

from .amendment import Amendment

__all__ = ["validate_amendment"]


def _is_structured_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def _contains_raw_code(changes: Mapping[str, Any]) -> bool:
    raw_keys = {"raw_code", "code_blob", "diff_text"}
    for key, value in changes.items():
        if key in raw_keys and isinstance(value, str):
            return True
        if isinstance(value, Mapping) and _contains_raw_code(value):
            return True
        if isinstance(value, list):
            if any(isinstance(item, str) and item.strip().startswith("def ") for item in value):
                return True
    return False


def validate_amendment(amendment: Amendment) -> List[str]:
    """Run structural and semantic validation rules."""

    errors: List[str] = []
    payload = amendment.to_dict()

    for key in ("summary", "reason"):
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Missing required field: {key}")

    changes = payload.get("changes")
    if not _is_structured_mapping(changes):
        errors.append("Changes must be a structured mapping")
        return errors

    if _contains_raw_code(changes):
        errors.append("Raw code blobs are not permitted in changes")

    touches_experiments = bool(changes.get("experiments"))
    touches_world = bool(changes.get("world"))
    if (touches_experiments or touches_world) and len(amendment.reason.strip()) < 10:
        errors.append("Experiment or world changes require a detailed rationale")

    metadata = payload.get("metadata")
    if metadata and not _is_structured_mapping(metadata):
        errors.append("Metadata, when provided, must be a mapping")

    return errors
