"""Quarantine helpers for Cathedral governance."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from .amendment import Amendment, amendment_digest

__all__ = ["quarantine_amendment"]


def _resolve_quarantine_dir() -> Path:
    override = os.getenv("SENTIENTOS_QUARANTINE_DIR")
    if override:
        return Path(override)
    return Path("C:/SentientOS/quarantine")


def quarantine_amendment(amendment: Amendment, errors: List[str]) -> str:
    """Persist a quarantined amendment and return the stored path."""

    directory = _resolve_quarantine_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{amendment.id}.json"
    payload = {
        "amendment": amendment.to_dict(),
        "errors": list(errors),
        "digest": amendment_digest(amendment),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "proposer": amendment.proposer,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(path)
