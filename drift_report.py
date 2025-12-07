"""Passive drift detection helpers for vow digest alignment.

Stage-0 federation primitive for surfacing digest drift without scheduling,
networking, or side effects. All helpers are purely informational.
"""
from __future__ import annotations


def generate_drift_report(local_digest: str, expected_digest: str) -> dict:
    """Return a deterministic drift report without mutating state.

    The report is informational only and performs no scheduling or network
    activity. It simply compares the provided digests and surfaces a structured
    summary for higher orchestration layers.
    """

    match = local_digest == expected_digest
    return {
        "local_digest": local_digest,
        "expected_digest": expected_digest,
        "match": match,
        "status": "ok" if match else "drift_detected",
    }
