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
