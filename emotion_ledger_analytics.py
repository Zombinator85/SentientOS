"""Summaries and drift detection for the emotional ledger."""

from __future__ import annotations

import json
from typing import Dict

import emotion_memory as em
import memory_manager as mm


def capture_snapshot() -> Dict[str, Dict[str, float]]:
    """Persist the current emotion averages and trend."""

    average = em.average_emotion()
    trend = em.trend()
    dominant = max(average, key=average.get) if average else ""
    severity = "stable"
    if any(abs(delta) > 0.25 for delta in trend.values()):
        severity = "surge"
    elif any(abs(delta) > 0.1 for delta in trend.values()):
        severity = "shift"

    payload = {"average": average, "trend": trend, "dominant": dominant, "severity": severity}
    mm.append_memory(
        json.dumps({"emotion_snapshot": payload}, ensure_ascii=False),
        tags=["emotion", "analytics", severity],
        source="emotion_analytics",
    )
    return payload


__all__ = ["capture_snapshot"]
