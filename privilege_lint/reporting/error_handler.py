from __future__ import annotations

import logging
from typing import Iterable


class ErrorHandler:
    """Resolve requested report formats with graceful fallbacks."""

    def __init__(self, default_format: str = "json", logger: logging.Logger | None = None) -> None:
        self.default_format = default_format
        self._logger = logger or logging.getLogger(__name__)

    def resolve(self, requested: str | None, available: Iterable[str]) -> str:
        if requested:
            fmt = requested.lower()
        else:
            fmt = self.default_format
        available_set = {name.lower() for name in available}
        if fmt in available_set:
            return fmt
        if requested:
            self._logger.warning(
                "Unsupported privilege lint report format '%s'; defaulting to '%s'.",
                requested,
                self.default_format,
            )
        return self.default_format
