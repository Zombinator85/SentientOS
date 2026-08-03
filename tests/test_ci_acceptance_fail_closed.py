from __future__ import annotations

from scripts.analyze_test_provenance import Thresholds, analyze
from scripts.validation_completion import classify_validation
import pytest

pytestmark = pytest.mark.no_legacy_skip


def _payload(**updates):
    payload = dict(pytest_exit_code=0, metrics_status="ok", reporter_ok=True,
                   collection_completed=True, tests_collected=1, tests_selected=1,
                   call_phase_outcome_count=1, tests_executed=1, tests_failed=0,
                   reporter_status="complete")
    payload.update(updates); return payload

def test_bootstrap_failure_is_insufficient_evidence(): assert classify_validation(_payload(pytest_exit_code=None)) == "bootstrap_failed"
def test_collection_failure_is_insufficient_evidence(): assert classify_validation(_payload(collection_completed=False)) == "collection_failed"
def test_zero_collected_tests_is_insufficient_evidence(): assert classify_validation(_payload(tests_collected=0)) == "zero_tests_collected"
def test_missing_metrics_is_insufficient_evidence(): assert classify_validation(_payload(metrics_status="unavailable")) == "metrics_missing"
def test_zero_call_phase_outcomes_is_insufficient_evidence(): assert classify_validation(_payload(call_phase_outcome_count=0)) == "zero_call_phase_outcomes"
def test_complete_execution_is_validation_complete(): assert classify_validation(_payload()) == "validation_complete"

def _thresholds(): return Thresholds(2, .15, .1, .5, .5, 3)
def test_trend_analysis_rejects_zero_run_window():
    report = analyze([], _thresholds())
    assert report["overall_status"] == "INSUFFICIENT_EVIDENCE" and report["insufficient_evidence"]
def test_integrity_ok_does_not_override_insufficient_validation():
    report = analyze([{"timestamp":"2026-01-01", "run_intent":"default", "validation_status":"bootstrap_failed"}], _thresholds())
    assert report["integrity_ok"] and report["overall_status"] == "INSUFFICIENT_EVIDENCE"
