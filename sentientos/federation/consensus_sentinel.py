"""Deterministic, read-only federation consensus sentinel."""

from __future__ import annotations

from collections import deque
from copy import deepcopy
from typing import Any, Deque, Mapping


class FederationConsensusSentinel:
    """Compare local digests against externally reported digests deterministically."""

    _DRIFT_ORDER = ("none", "minor", "major", "catastrophic")

    def __init__(self, max_reports: int = 20) -> None:
        self.max_reports = max(int(max_reports), 1)
        self._reports: Deque[dict[str, Any]] = deque(maxlen=self.max_reports)

    def record_external_digest(self, digest: Mapping[str, Any]) -> None:
        """Store an external digest snapshot defensively in FIFO order."""

        self._reports.append(deepcopy(digest or {}))

    def compare(self, local_digest: Mapping[str, Any]) -> dict:
        """Compare the provided local digest against stored external digests."""

        local_snapshot = deepcopy(local_digest or {})
        external_reports = list(self._reports)

        classifications = [self._classify(local_snapshot, report) for report in external_reports]
        drift_level = self._aggregate_drift_level(classifications)
        matching = [
            self._digest_value(report)
            for report in external_reports
            if self._digests_match(local_snapshot, report)
        ]

        signals = {
            "external_reports": len(external_reports),
            "matches": matching,
            "classifications": classifications,
        }

        match = bool(matching) or not external_reports and drift_level == "none"
        return {"match": match, "drift_level": drift_level, "signals": signals}

    def _digests_match(self, local: Mapping[str, Any], external: Mapping[str, Any]) -> bool:
        return self._digest_value(local) == self._digest_value(external)

    def _digest_value(self, payload: Mapping[str, Any]) -> str:
        if not isinstance(payload, Mapping):
            return ""
        digest = payload.get("digest")
        return str(digest) if digest is not None else ""

    def _classify(self, local: Mapping[str, Any], external: Mapping[str, Any]) -> dict:
        local_components = self._components(local)
        external_components = self._components(external)

        identity_match = self._identity_class(local_components["identity"]) == self._identity_class(
            external_components["identity"]
        )
        mismatched_fields = self._mismatched_fields(
            local_components["config"], external_components["config"]
        )
        level = self._determine_level(
            identity_match,
            mismatched_fields,
            local_components["config"],
            external_components["config"],
        )

        return {
            "digest": self._digest_value(external),
            "identity_match": identity_match,
            "mismatched_fields": mismatched_fields,
            "level": level,
        }

    def _components(self, payload: Mapping[str, Any]) -> dict:
        if not isinstance(payload, Mapping):
            return {"identity": {}, "config": {}}
        components = payload.get("components")
        if not isinstance(components, Mapping):
            return {"identity": {}, "config": {}}
        identity = components.get("identity") if isinstance(components, Mapping) else {}
        config = components.get("config") if isinstance(components, Mapping) else {}
        return {
            "identity": deepcopy(identity) if isinstance(identity, Mapping) else {},
            "config": deepcopy(config) if isinstance(config, Mapping) else {},
        }

    def _identity_class(self, identity: Mapping[str, Any]) -> tuple:
        if not isinstance(identity, Mapping):
            return tuple()
        core = identity.get("core_themes")
        if not isinstance(core, Mapping):
            return tuple()
        return tuple((str(key), core.get(key)) for key in sorted(core))

    def _mismatched_fields(self, local_config: Mapping[str, Any], external_config: Mapping[str, Any]) -> list[str]:
        if not isinstance(local_config, Mapping):
            local_config = {}
        if not isinstance(external_config, Mapping):
            external_config = {}
        fields = sorted(set(local_config.keys()) | set(external_config.keys()))
        mismatches: list[str] = []
        for field in fields:
            if self._normalise(local_config.get(field)) != self._normalise(external_config.get(field)):
                mismatches.append(field)
        return mismatches

    def _determine_level(
        self,
        identity_match: bool,
        mismatched_fields: list[str],
        local_config: Mapping[str, Any],
        external_config: Mapping[str, Any],
    ) -> str:
        total_fields = len(set(local_config.keys()) | set(external_config.keys()))
        if identity_match and not mismatched_fields:
            return "none"
        if identity_match:
            return "minor"
        if not mismatched_fields:
            return "major"
        if mismatched_fields and len(mismatched_fields) < max(total_fields, 1):
            return "major"
        if total_fields == 0:
            return "major"
        return "catastrophic"

    def _normalise(self, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(k): self._normalise(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
        if isinstance(value, (list, tuple)):
            return [self._normalise(v) for v in value]
        return value

    def _aggregate_drift_level(self, classifications: list[dict]) -> str:
        highest_index = 0
        for entry in classifications:
            level = entry.get("level")
            if isinstance(level, str) and level in self._DRIFT_ORDER:
                highest_index = max(highest_index, self._DRIFT_ORDER.index(level))
        return self._DRIFT_ORDER[highest_index]


__all__ = ["FederationConsensusSentinel"]
