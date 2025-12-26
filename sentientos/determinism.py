"""Deterministic seeding helpers for SentientOS autonomous services."""

from __future__ import annotations

import logging
import os
import random
from typing import Optional

from .config import RuntimeConfig
from .optional_deps import dependency_available, optional_import

LOGGER = logging.getLogger(__name__)

_DEFAULT_SEED = 1337


def resolve_seed(config: Optional[RuntimeConfig] = None, override: Optional[int] = None) -> int:
    """Return the seed that should be used for deterministic execution."""

    if override is not None:
        return int(override)
    env_value = os.environ.get("SENTIENTOS_SEED")
    if env_value not in (None, ""):
        try:
            return int(env_value)
        except ValueError:
            LOGGER.warning("Invalid SENTIENTOS_SEED value: %s", env_value)
    if config and config.determinism.seed is not None:
        return int(config.determinism.seed)
    return _DEFAULT_SEED


def seed_everything(
    config: Optional[RuntimeConfig] = None,
    *,
    override: Optional[int] = None,
) -> int:
    """Seed the Python ecosystem for reproducible behaviour.

    The function attempts to seed ``random``, ``numpy`` and ``torch`` if present.
    The seed used is returned for logging purposes.
    """

    seed = resolve_seed(config, override)
    random.seed(seed)

    numpy = optional_import("numpy", feature="determinism_seed") if dependency_available("numpy") else None
    if numpy is not None:
        numpy.random.seed(seed)

    torch = optional_import("torch", feature="determinism_seed") if dependency_available("torch") else None
    if torch is not None:
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)

    return seed


__all__ = ["seed_everything", "resolve_seed"]
