"""SentientOS runtime facade wiring inner-world orchestrator into core loop."""

from __future__ import annotations

import logging

from sentientos.cognition import CognitiveSurface
from sentientos.innerworld import InnerWorldOrchestrator

from .core_loop import CoreLoop
from .interfaces import CycleInput, CycleOutput

LOGGER = logging.getLogger(__name__)


class Runtime:
    """Lightweight runtime controller exposing the core cognition loop."""

    def __init__(
        self,
        *,
        innerworld: InnerWorldOrchestrator | None = None,
        cognitive_surface: CognitiveSurface | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.innerworld = innerworld or InnerWorldOrchestrator()
        self._logger = logger or LOGGER
        self.core_loop = CoreLoop(self.innerworld, cognitive_surface=cognitive_surface, logger=self._logger)

    def run_cycle(self, cycle_state: CycleInput) -> CycleOutput:
        """Run a single cognition cycle through the core loop."""

        return self.core_loop.run_cycle(cycle_state)
