from __future__ import annotations

import hashlib
import json
import math
from typing import Any

SCHEMA_VERSION = "sentientos.behavioral_witness:v1"
MAX_PER_NODE = 32
MAX_PER_RUN = 128
MAX_FACT_BYTES = 64 * 1024
MAX_DEPTH = 8
MAX_KEYS = 256
MAX_LIST_ITEMS = 1024
MAX_STRING = 4096
MAX_IDENTIFIER = 128


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def normalize_facts(value: object) -> object:
    seen: set[int] = set()

    def visit(item: object, depth: int) -> object:
        if depth > MAX_DEPTH:
            raise ValueError("behavioral witness facts exceed nesting depth")
        if item is None or isinstance(item, (bool, int, str)):
            if isinstance(item, str) and len(item) > MAX_STRING:
                raise ValueError("behavioral witness string is too long")
            return item
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("behavioral witness floats must be finite")
            return item
        if isinstance(item, (list, dict)):
            identity = id(item)
            if identity in seen:
                raise ValueError("recursive behavioral witness facts")
            seen.add(identity)
            try:
                if isinstance(item, list):
                    if len(item) > MAX_LIST_ITEMS:
                        raise ValueError("behavioral witness list is too large")
                    return [visit(child, depth + 1) for child in item]
                if len(item) > MAX_KEYS:
                    raise ValueError("behavioral witness mapping has too many keys")
                if not all(isinstance(key, str) for key in item):
                    raise ValueError("behavioral witness mapping keys must be strings")
                return {key: visit(item[key], depth + 1) for key in sorted(item)}
            finally:
                seen.remove(identity)
        raise ValueError("behavioral witness facts must contain only JSON values")

    normalized = visit(value, 0)
    if not isinstance(normalized, dict):
        raise ValueError("behavioral witness facts must be an object")
    if len(canonical_bytes(normalized)) > MAX_FACT_BYTES:
        raise ValueError("behavioral witness facts exceed 64 KiB")
    return normalized


def build_witness(*, repository_sha: str, run_id: str, node_id: str, contract_id: str,
                  witness_kind: str, facts: object, phase: str = "call") -> dict[str, object]:
    if not contract_id or len(contract_id) > MAX_IDENTIFIER:
        raise ValueError("invalid behavioral witness contract ID")
    if not witness_kind or len(witness_kind) > MAX_IDENTIFIER:
        raise ValueError("invalid behavioral witness kind")
    if not repository_sha or not run_id or not node_id or phase != "call":
        raise ValueError("behavioral witness requires bound call-phase context")
    frozen = normalize_facts(facts)
    witness: dict[str, object] = {
        "schema_version": SCHEMA_VERSION, "repository_sha": repository_sha,
        "run_id": run_id, "node_id": node_id, "phase": phase,
        "contract_id": contract_id, "witness_kind": witness_kind, "facts": frozen,
        "facts_digest": digest(frozen),
    }
    witness["digest"] = digest(witness)
    return witness


def valid_witness(value: object) -> bool:
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        return False
    try:
        rebuilt = build_witness(**{key: value[key] for key in (
            "repository_sha", "run_id", "node_id", "contract_id", "witness_kind", "facts", "phase")})
    except (KeyError, TypeError, ValueError):
        return False
    return rebuilt == value

