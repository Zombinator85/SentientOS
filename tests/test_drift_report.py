import pytest

from drift_report import generate_drift_report

pytestmark = pytest.mark.no_legacy_skip


def test_generate_drift_report_match():
    report = generate_drift_report("abc", "abc")
    assert report == {
        "local_digest": "abc",
        "expected_digest": "abc",
        "match": True,
        "status": "ok",
    }


def test_generate_drift_report_drift():
    report = generate_drift_report("abc", "xyz")
    assert report == {
        "local_digest": "abc",
        "expected_digest": "xyz",
        "match": False,
        "status": "drift_detected",
    }


def test_generate_drift_report_deterministic():
    first = generate_drift_report("123", "456")
    second = generate_drift_report("123", "456")
    assert first == second
