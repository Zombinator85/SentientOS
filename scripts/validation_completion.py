"""Canonical fail-closed classification for executable pytest validation."""

from __future__ import annotations

from typing import Any, Mapping

VALIDATION_STATUSES = frozenset({
    "bootstrap_failed", "collection_failed", "zero_tests_collected",
    "zero_call_phase_outcomes", "metrics_missing", "validation_failed",
    "validation_complete",
})


def classify_validation(payload: Mapping[str, Any]) -> str:
    """Classify reporter/provenance state without inferring missing evidence."""
    exit_code = payload.get("pytest_exit_code")
    if exit_code is None:
        return "bootstrap_failed"
    if type(exit_code) is not int:
        return "validation_failed"
    if payload.get("metrics_status") != "ok" or not payload.get("reporter_ok"):
        return "metrics_missing"
    if not payload.get("collection_completed"):
        return "collection_failed"
    collected = payload.get("tests_collected")
    selected = payload.get("tests_selected")
    if exit_code == 5 or type(collected) is not int or collected <= 0 or type(selected) is not int or selected <= 0:
        return "zero_tests_collected"
    call_count = payload.get("call_phase_outcome_count")
    executed = payload.get("tests_executed")
    if type(call_count) is not int or call_count <= 0 or type(executed) is not int or executed <= 0:
        return "zero_call_phase_outcomes"
    if (exit_code != 0 or type(payload.get("tests_failed")) is not int
            or payload.get("tests_failed") != 0 or payload.get("reporter_status") != "complete"):
        return "validation_failed"
    return "validation_complete"


def is_validation_complete(payload: Mapping[str, Any]) -> bool:
    return classify_validation(payload) == "validation_complete"
