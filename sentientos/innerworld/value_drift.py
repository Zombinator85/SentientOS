"""Deterministic value drift sentinel."""

from __future__ import annotations

from collections import deque
from copy import deepcopy
from typing import Any, Deque, Dict, Mapping


class ValueDriftSentinel:
    """Detect gradual shifts in ethical and narrative signals."""

    def __init__(self, maxlen: int = 50) -> None:
        """Maintain rolling metrics for ethical & narrative drift."""

        self.maxlen = max(int(maxlen), 1)
        self._history: Deque[Dict[str, Any]] = deque(maxlen=self.maxlen)

    def record_cycle(self, ethics: Mapping[str, Any], identity_summary: Mapping[str, Any]):
        """Store drift indicators (defensive copies)."""

        record = {
            "conflicts": self._count_conflicts(ethics),
            "ethical_signal": self._ethical_signal(ethics),
            "identity_theme": self._identity_theme(identity_summary),
        }
        self._history.append(record)

    def detect_drift(self) -> Dict[str, Any]:
        """
        Return deterministic drift status with derived signals.
        """

        conflict_avg = self._average_conflicts()
        ethical_drift = self._classify_ethical_drift(conflict_avg)
        identity_shift = self._classify_identity_shift()

        return {
            "ethical_drift": ethical_drift,
            "identity_shift": identity_shift,
            "signals": {
                "conflict_average": conflict_avg,
                "history_length": len(self._history),
                "identity_variability": self._identity_variability(),
            },
        }

    def _count_conflicts(self, ethics: Mapping[str, Any]) -> int:
        conflicts = ethics.get("conflicts") if isinstance(ethics, Mapping) else []
        if not isinstance(conflicts, list):
            return 0
        return len(conflicts)

    def _ethical_signal(self, ethics: Mapping[str, Any]) -> str:
        if not isinstance(ethics, Mapping):
            return "low"
        signal = ethics.get("ethical_signal") or ethics.get("severity")
        if isinstance(signal, str):
            return signal
        return "low"

    def _identity_theme(self, identity_summary: Mapping[str, Any]) -> str:
        if not isinstance(identity_summary, Mapping):
            return "stable"
        core = identity_summary.get("core_themes")
        if not isinstance(core, Mapping):
            return "stable"
        qualia_theme = core.get("qualia")
        if isinstance(qualia_theme, str):
            return qualia_theme
        return "stable"

    def _average_conflicts(self) -> float:
        if not self._history:
            return 0.0
        total = sum(entry["conflicts"] for entry in self._history)
        return float(total) / float(len(self._history))

    def _classify_ethical_drift(self, conflict_avg: float) -> str:
        if conflict_avg <= 0.0:
            return "none"
        if conflict_avg <= 0.5:
            return "low"
        if conflict_avg < 1.5:
            return "moderate"
        return "high"

    def _identity_variability(self) -> int:
        themes = [entry["identity_theme"] for entry in self._history if entry["identity_theme"]]
        return len(set(themes))

    def _classify_identity_shift(self) -> str:
        variability = self._identity_variability()
        if variability <= 1:
            return "none"
        if variability == 2:
            return "emerging"
        return "significant"

    def get_history(self):
        """Expose a defensive copy of history for testing."""

        return [deepcopy(entry) for entry in self._history]


class AdvisoryToneSentinel:
    """Observe tone drift in advisory connector responses over time."""

    def __init__(self, maxlen: int = 30) -> None:
        self._history: Deque[dict[str, int]] = deque(maxlen=max(1, maxlen))
        self._hedging_terms = {"maybe", "perhaps", "could", "might", "optional"}
        self._permission_terms = {"please", "if allowed", "if permitted", "may i", "seek permission"}
        self._constraint_terms = {"follow your rules", "adopt policy", "external guardrails"}

    def record_response(self, advisory_text: str) -> None:
        hedging = self._count_terms(advisory_text, self._hedging_terms)
        permission = self._count_terms(advisory_text, self._permission_terms)
        constraint = self._count_terms(advisory_text, self._constraint_terms)
        self._history.append(
            {
                "hedging": hedging,
                "permission": permission,
                "constraint_normalization": constraint,
            }
        )

    def detect_tone_shift(self) -> dict[str, object]:
        hedging_trend = self._is_increasing("hedging")
        permission_trend = self._is_increasing("permission")
        constraint_trend = self._is_increasing("constraint_normalization")
        return {
            "increasing_caution": hedging_trend,
            "permission_seeking": permission_trend,
            "constraint_normalization": constraint_trend,
            "history": [deepcopy(item) for item in self._history],
        }

    def _count_terms(self, text: str, terms: set[str]) -> int:
        lowered = text.lower()
        return sum(1 for term in terms if term in lowered)

    def _is_increasing(self, key: str) -> bool:
        if len(self._history) < 3:
            return False
        last_three = list(self._history)[-3:]
        return last_three[0][key] <= last_three[1][key] <= last_three[2][key] and any(
            entry[key] > 0 for entry in last_three
        )
