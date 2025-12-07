"""Stage 0 scaffolding for SentientOS inner experience management."""

from __future__ import annotations

import logging
from typing import Dict


class InnerExperience:
    """Track and expose the agent's inner experiential signals."""

    DEFAULT_CHANNELS = {
        "confidence": 0.5,
        "novelty": 0.5,
        "tension": 0.5,
        "satisfaction": 0.5,
    }

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)
        self._state: Dict[str, float] = {}
        self.reset()

    def reset(self) -> None:
        """Reset the inner experience state to its baseline configuration."""
        self._state = dict(self.DEFAULT_CHANNELS)
        self._logger.debug("InnerExperience reset to baseline: %s", self._state)

    def update_signal(self, name: str, value: float) -> None:
        """Record or update a named experiential signal."""
        clamped = max(0.0, min(1.0, float(value)))
        self._state[name] = clamped
        self._logger.debug("Signal '%s' updated to %s (clamped from %s)", name, clamped, value)

    def integrate_signals(self, **kwargs: float) -> None:
        """Blend external signals into the qualia state using deterministic rules."""

        def clamp(value: float) -> float:
            return max(0.0, min(1.0, value))

        if "errors" in kwargs:
            errors = float(kwargs["errors"])
            self.update_signal(
                "tension", self._state.get("tension", 0.5) + 0.1 * errors
            )
            self.update_signal(
                "confidence", self._state.get("confidence", 0.5) - 0.05 * errors
            )

        if "progress" in kwargs:
            progress = float(kwargs["progress"])
            self.update_signal(
                "satisfaction",
                self._state.get("satisfaction", 0.5) + 0.5 * progress,
            )
            self.update_signal(
                "confidence", self._state.get("confidence", 0.5) + 0.2 * progress
            )

        if "novelty" in kwargs:
            incoming = clamp(float(kwargs["novelty"]))
            blended = 0.7 * self._state.get("novelty", 0.5) + 0.3 * incoming
            self.update_signal("novelty", blended)
            self._logger.debug(
                "Novelty integrated: current=%s incoming=%s blended=%s",
                self._state.get("novelty"),
                incoming,
                blended,
            )

    def get_state(self) -> Dict[str, float]:
        """Retrieve the current inner experience state."""
        return dict(self._state)
