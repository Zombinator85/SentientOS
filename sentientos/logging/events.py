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


def log_ethics_report(report: Dict[str, Any]) -> None:
    """Emit a debug-level summary of an ethical evaluation."""

    logger.debug(
        f"[ethics] conflicts={report.get('conflicts')} values={report.get('values')}"
    )


def log_history_summary(summary: Dict[str, Any]) -> None:
    """Emit a debug-level summary of the current cycle history."""

    logger.debug(f"[innerworld-history] summary={summary}")


def log_debug_reflection(summary: Dict[str, Any]) -> None:
    """Emit a debug-level summary of the current reflection snapshot."""

    logger.debug(f"[innerworld-reflection] summary={summary}")


def log_debug_cognitive_report(report: Dict[str, Any]) -> None:
    """Emit a debug-level summary of the current cognitive report."""

    logger.debug(f"[cognitive-report] report={report}")


def log_debug_narrative(summary: Dict[str, Any]) -> None:
    """Emit a debug-level summary of the current narrative snapshot."""

    logger.debug(f"[narrative] identity_summary={summary}")
