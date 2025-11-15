"""Node identity helpers for the SentientOS federation layer."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

__all__ = ["NodeId", "compute_fingerprint", "build_node_id_payload"]


@dataclass(frozen=True)
class NodeId:
    """Stable identity tuple for a SentientOS node."""

    name: str
    fingerprint: str


def _normalise_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a JSON-serialisable mapping for hashing purposes."""

    def _normalise(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(k): _normalise(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
        if isinstance(value, (list, tuple)):
            return [_normalise(v) for v in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return repr(value)

    return _normalise(dict(config))  # type: ignore[arg-type]


def compute_fingerprint(*, node_name: str, runtime_root: Path, config: Mapping[str, Any]) -> str:
    """Compute a short, deterministic fingerprint for the node."""

    payload = {
        "node": node_name,
        "root": str(runtime_root),
        "config": _normalise_config(config),
    }
    serialised = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialised.encode("utf-8")).hexdigest()
    return digest[:12]


def build_node_id_payload(node_name: str, fingerprint: str) -> NodeId:
    """Build a :class:`NodeId` ensuring canonical casing."""

    return NodeId(name=str(node_name), fingerprint=str(fingerprint))
