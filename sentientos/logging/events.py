"""Structured event logging helpers."""

from __future__ import annotations

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def log_innerworld_cycle(report: Dict[str, Any]) -> None:
    """Emit a debug-level summary of an inner-world cycle."""

    logger.debug(
        f"[innerworld] cycle={report.get('cycle_id')} "
        f"qualia={report.get('qualia')} meta={report.get('meta')}"
    )


def log_simulation_cycle(report: Dict[str, Any]) -> None:
    """Emit a debug-level summary of an inner-world simulation cycle."""

    logger.debug(
        f"[innerworld-sim] qualia={report['report'].get('qualia')} "
        f"meta={report['report'].get('metacog')}"
    )
