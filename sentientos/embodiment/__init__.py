"""Simulation-only embodiment interface contracts."""

from .contracts import (
    EmbodimentContract,
    SignalDefinition,
    SignalDirection,
    SignalType,
    get_embodiment_contract,
    get_signal_definition,
    list_embodiment_contracts,
)
from .embodiment_digest import get_recent_embodiment_digest
from .simulation import SimulationResult, simulate_signal

__all__ = [
    "EmbodimentContract",
    "SignalDefinition",
    "SignalDirection",
    "SignalType",
    "SimulationResult",
    "get_recent_embodiment_digest",
    "get_embodiment_contract",
    "get_signal_definition",
    "list_embodiment_contracts",
    "simulate_signal",
]
