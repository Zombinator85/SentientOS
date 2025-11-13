"""Base classes for experiment adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class Adapter(ABC):
    """Abstract base class for experiment adapters."""

    #: Human-readable adapter name. Subclasses should override this.
    name: str = "base"
    #: Whether the adapter yields deterministic results for a fixed input.
    deterministic: bool = True

    @abstractmethod
    def connect(self) -> None:
        """Establish the connection to the underlying resource."""

    @abstractmethod
    def perform(self, action: Dict[str, Any]) -> None:
        """Execute an action against the adapter."""

    @abstractmethod
    def read(self, measure: Dict[str, Any]) -> Any:
        """Read a measurement from the adapter."""

    @abstractmethod
    def close(self) -> None:
        """Tear down the connection and release resources."""
