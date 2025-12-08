"""Deterministic configuration sanitization helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


_DEFAULT_ALLOWED_FIELDS = (
    "model",
    "version",
    "templates",
    "identity_constraints",
    "drift_thresholds",
    "spotlight_rules",
    "dialogue_rules",
    "core_values",
    "tone_constraints",
    "ethical_rules",
    "dialogue_templates",
)


class ConfigSanitizer:
    """Produce deterministic, defensive configuration snapshots."""

    def __init__(self, allowed_fields: list[str] | None = None) -> None:
        """Initialize with deterministic field allowlist."""

        fields = allowed_fields if allowed_fields is not None else list(_DEFAULT_ALLOWED_FIELDS)
        self.allowed_fields = tuple(str(field) for field in fields)

    def sanitize(self, config: Mapping[str, Any] | None) -> dict:
        """Produce a deterministic, deeply sorted, defensive-copied snapshot."""

        base_config: Mapping[str, Any] = config or {}
        sanitized = self._sanitize_dict(base_config, root=True)
        return {"config": sanitized}

    def _sanitize_dict(self, data: Mapping[str, Any], root: bool = False) -> dict:
        if not isinstance(data, Mapping):
            return {}

        allowed = set(self.allowed_fields) if root else None
        sanitized: dict[str, Any] = {}
        for key in sorted(data, key=lambda item: str(item)):
            key_str = str(key)
            if self._is_disallowed_key(key_str):
                continue
            if allowed is not None and key_str not in allowed:
                continue

            value = self._sanitize_value(data[key])
            sanitized[key_str] = value
        return sanitized

    def _sanitize_list(self, items: list[Any]) -> list[Any]:
        sanitized_items = [self._sanitize_value(item) for item in items]
        try:
            return sorted(sanitized_items)
        except TypeError:
            return sanitized_items

    def _sanitize_value(self, value: Any) -> Any:
        if isinstance(value, Mapping):
            return self._sanitize_dict(value)
        if isinstance(value, list):
            return self._sanitize_list(value)
        if isinstance(value, tuple):
            return self._sanitize_list(list(value))
        if isinstance(value, (str, int, float, bool)) or value is None:
            return deepcopy(value)
        return repr(value)

    def _is_disallowed_key(self, key: str) -> bool:
        key_lower = key.lower()
        forbidden_tokens = (
            "time",
            "timestamp",
            "uuid",
            "seed",
            "counter",
            "session",
            "env",
        )
        return any(token in key_lower for token in forbidden_tokens)


__all__ = ["ConfigSanitizer"]
