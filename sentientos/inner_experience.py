"""Stage 0 scaffolding for SentientOS inner experience management."""

from __future__ import annotations

from typing import Dict


class InnerExperience:
    """Track and expose the agent's inner experiential signals."""

    def reset(self) -> None:
        """Reset the inner experience state to its baseline configuration."""
        raise NotImplementedError("InnerExperience.reset is not implemented yet")

    def update_signal(self, name: str, value: float) -> None:
        """Record or update a named experiential signal."""
        raise NotImplementedError("InnerExperience.update_signal is not implemented yet")

    def get_state(self) -> Dict[str, float]:
        """Retrieve the current inner experience state."""
        raise NotImplementedError("InnerExperience.get_state is not implemented yet")
