"""Deterministic mock adapter for experiments."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, DefaultDict, Dict, List

from .base import Adapter


class MockAdapter(Adapter):
    """Purely deterministic adapter for CI and demos."""

    name = "mock"
    deterministic = True

    def __init__(self) -> None:
        self._connected = False
        self._actions: List[Dict[str, Any]] = []
        self._measure_counts: DefaultDict[str, int] = defaultdict(int)

    @property
    def recorded_actions(self) -> List[Dict[str, Any]]:
        """Return the actions recorded for inspection in tests."""

        return list(self._actions)

    def connect(self) -> None:
        self._connected = True

    def perform(self, action: Dict[str, Any]) -> None:
        if not isinstance(action, dict):
            raise TypeError("action must be a dictionary")
        if not self._connected:
            raise RuntimeError("adapter not connected")
        self._actions.append(dict(action))

    def read(self, measure: Dict[str, Any]) -> Any:
        if not isinstance(measure, dict):
            raise TypeError("measure must be a dictionary")
        if not self._connected:
            raise RuntimeError("adapter not connected")
        kind = str(measure.get("kind", "")).strip()
        if not kind:
            raise ValueError("measure must include a 'kind' field")
        index = self._measure_counts[kind]
        self._measure_counts[kind] += 1
        if kind == "temp_c":
            return 21.5 + index * 0.1
        if kind == "avg_r":
            return 100 + index
        if kind == "avg_g":
            return 90 + index
        if kind == "avg_b":
            return 80 + index
        if kind == "humidity_pct":
            return 45.0 + index * 0.2
        # Default deterministic fallback: echo the counter.
        return {"count": index, "kind": kind}

    def close(self) -> None:
        self._connected = False
