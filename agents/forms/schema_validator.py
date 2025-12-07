"""Schema validation helpers for SSA form agents."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def _validate_value(value: Any, schema: Dict[str, Any]) -> bool:
    schema_type = schema.get("type")

    if schema_type == "object":
        if not isinstance(value, dict):
            return False
        properties = schema.get("properties", {})
        for key, prop_schema in properties.items():
            if key in value and not _validate_value(value[key], prop_schema):
                return False
        return True

    if schema_type == "array":
        if not isinstance(value, list):
            return False
        item_schema = schema.get("items")
        if item_schema is None:
            return True
        return all(_validate_value(item, item_schema) for item in value)

    if schema_type == "string":
        return isinstance(value, str)

    if schema_type == "boolean":
        return isinstance(value, bool)

    # Unknown or unsupported type defaults to pass-through to avoid false negatives
    return True


def validate_profile(profile: Dict[str, Any], schema_path: str) -> bool:
    """Validate a claimant profile against the provided JSON schema.

    The validator is deterministic and returns a boolean without raising.
    """
    try:
        schema_content = Path(schema_path).read_text(encoding="utf-8")
        schema = json.loads(schema_content)
    except (OSError, json.JSONDecodeError):
        return False

    if not isinstance(profile, dict):
        return False

    return _validate_value(profile, schema)
