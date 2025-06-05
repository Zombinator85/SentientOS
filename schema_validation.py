"""Minimal JSON payload validation helpers."""

from typing import Any, Mapping, Tuple


def validate_payload(data: Any, schema: Mapping[str, type]) -> Tuple[bool, str | None]:
    """Validate ``data`` against ``schema``.

    Schema is a mapping of field name to Python type. Missing or wrong types
    return ``False`` and an error key.
    """
    if not isinstance(data, dict):
        return False, "malformed_json"
    for field, typ in schema.items():
        if field not in data:
            return False, "missing_field"
        if not isinstance(data[field], typ):
            return False, "invalid_type"
    return True, None
