"""Consensus helpers for experiment federation safety."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict


_CRITICAL_FIELDS = [
    "description",
    "conditions",
    "expected",
    "criteria",
    "actions",
    "action",
    "adapters",
    "adapter",
    "metadata",
    "proposer",
    "proposed_at",
    "requires_consensus",
    "quorum_k",
    "quorum_n",
]


def _canonical_spec(exp: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the fields that participate in consensus digests."""
    canonical: Dict[str, Any] = {}
    for field in _CRITICAL_FIELDS:
        if field in exp:
            canonical[field] = exp[field]
    return canonical


def compute_experiment_digest(exp: Dict[str, Any]) -> str:
    """Return a stable SHA-256 digest of critical experiment fields."""

    if not isinstance(exp, dict):  # pragma: no cover - defensive
        raise TypeError("Experiment specification must be a dictionary")

    canonical = _canonical_spec(exp)
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

