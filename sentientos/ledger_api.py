"""Public append-only ledger facade for expressive callers.

This module is a boundary facade: it delegates writes to the existing canonical
JSONL append behavior and does not own truth-source semantics.
"""
from __future__ import annotations

from pathlib import Path
from typing import Mapping

from sentientos.attestation import append_jsonl


def append_audit_record(path: Path, record: Mapping[str, object]) -> dict[str, object]:
    """Append ``record`` to ``path`` using canonical append-only JSONL behavior.

    The facade intentionally performs only minimal normalization (dict copy) and
    delegates persistence semantics to the existing canonical append utility.
    """
    payload = dict(record)
    append_jsonl(path, payload)
    return payload
