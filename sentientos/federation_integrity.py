from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sentientos.event_stream import record_forge_event
from sentientos.integrity_snapshot import evaluate_peer_integrity


def federation_integrity_gate(repo_root: Path, *, context: str) -> dict[str, Any]:
    status = evaluate_peer_integrity(repo_root)
    warn = os.getenv("SENTIENTOS_FEDERATION_INTEGRITY_WARN", "0") == "1"
    enforce = os.getenv("SENTIENTOS_FEDERATION_INTEGRITY_ENFORCE", "0") == "1"
    allow_divergence = os.getenv("SENTIENTOS_FEDERATION_ALLOW_DIVERGENCE", "0") == "1"

    diverged = status.get("status") == "diverged"
    blocked = bool(diverged and enforce and not allow_divergence)

    if diverged and warn:
        record_forge_event(
            {
                "event": "federation_integrity_diverged",
                "level": "warning",
                "context": context,
                "reasons": status.get("divergence_reasons", []),
            }
        )
    if diverged and allow_divergence:
        record_forge_event(
            {
                "event": "federation_integrity_override",
                "level": "warning",
                "context": context,
                "note": "SENTIENTOS_FEDERATION_ALLOW_DIVERGENCE=1",
                "reasons": status.get("divergence_reasons", []),
            }
        )

    return {
        "status": status.get("status", "unknown"),
        "divergence_reasons": status.get("divergence_reasons", []),
        "peer_summaries": status.get("peer_summaries", []),
        "blocked": blocked,
    }
