from __future__ import annotations

import hashlib
import json
from typing import Any

GENESIS_PREV_HASH = "GENESIS"
HASH_ALGO = "sha256"
HASH_FIELDS = frozenset({"hash_algo", "prev_provenance_hash", "provenance_hash"})


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def payload_without_hash_fields(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in HASH_FIELDS}


def compute_provenance_hash(payload: dict[str, Any], prev_provenance_hash: str | None) -> str:
    material = payload_without_hash_fields(payload)
    prev_marker = prev_provenance_hash or GENESIS_PREV_HASH
    digest = hashlib.sha256()
    digest.update(prev_marker.encode("utf-8"))
    digest.update(b"\n")
    digest.update(canonical_json_bytes(material))
    return digest.hexdigest()
