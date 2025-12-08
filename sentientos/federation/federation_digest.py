"""Deterministic, read-only federation digest generator."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Iterable, Mapping

_DEFAULT_FIELDS = (
    "core_values",
    "tone_constraints",
    "ethical_rules",
    "dialogue_templates",
    "spotlight_rules",
    "drift_thresholds",
)


class FederationDigest:
    """Compute canonical digests over identity and configuration snapshots."""

    def __init__(self, fields: list[str] | None = None) -> None:
        """Initialize the digest generator with a deterministic field list."""

        base_fields: Iterable[str] = fields if fields is not None else _DEFAULT_FIELDS
        self.fields = tuple(str(field) for field in base_fields)

    def compute_digest(self, identity_summary: Mapping[str, Any], config: Mapping[str, Any]) -> dict:
        """Generate a stable digest for the provided identity and config snapshots."""

        identity_snapshot = deepcopy(identity_summary or {})
        # Config is guaranteed sanitized and deterministic by ConfigSanitizer.
        config_snapshot = deepcopy(config or {})

        components = {
            "fields": list(self.fields),
            "identity": self._normalise_identity(identity_snapshot),
            "config": self._normalise_config(config_snapshot),
        }
        serialised = json.dumps(components, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest_hex = hashlib.sha256(serialised).hexdigest()

        return {"digest": digest_hex, "components": components}

    def _normalise_identity(self, identity_summary: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(identity_summary, Mapping):
            return {}

        identity_payload: dict[str, Any] = {}
        if "core_themes" in identity_summary:
            identity_payload["core_themes"] = self._normalise(identity_summary.get("core_themes"))
        if "recurring_insights" in identity_summary:
            identity_payload["recurring_insights"] = self._normalise(
                identity_summary.get("recurring_insights")
            )
        if "chapter_count" in identity_summary:
            identity_payload["chapter_count"] = self._normalise(identity_summary.get("chapter_count"))

        return identity_payload

    def _normalise_config(self, config: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(config, Mapping):
            return {field: None for field in self.fields}

        payload: dict[str, Any] = {}
        for field in self.fields:
            payload[field] = self._normalise(config.get(field))
        return payload

    def _normalise(self, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                str(key): self._normalise(sub_value)
                for key, sub_value in sorted(value.items(), key=lambda item: str(item[0]))
            }
        if isinstance(value, (list, tuple)):
            return [self._normalise(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return repr(value)


__all__ = ["FederationDigest"]
