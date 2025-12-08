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


def log_debug_spotlight(data: Dict[str, Any]):
    """Emit debug information for workspace spotlight."""

    logger.debug(f"[spotlight] {data}")


def log_debug_dialogue(lines: list):
    """Emit debug information for inner dialogue lines."""

    logger.debug(f"[dialogue] {lines}")


def log_debug_value_drift(drift: Dict[str, Any]):
    """Emit debug information for value drift."""

    logger.debug(f"[value-drift] {drift}")


def log_debug_autobio(entries: list):
    """Emit debug information for autobiography entries."""

    logger.debug(f"[autobio] entries={entries}")


def log_debug_federation_digest(data: dict):
    """Emit debug information for federation digest snapshots."""

    logger.debug(f"[federation-digest] {data}")


def log_debug_federation_consensus(report: dict):
    """Emit debug information for federation consensus reports."""

    logger.debug(f"[federation-consensus] {report}")
