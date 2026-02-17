from __future__ import annotations

from sentientos.forge_failures import harvest_failures


def test_harvest_parses_pytest_failed_lines() -> None:
    stdout = """
FAILED tests/test_alpha.py::test_one - AssertionError: expected 1 == 2
FAILED tests/test_beta.py::test_two - ModuleNotFoundError: No module named 'x'
========================= 2 failed, 10 passed in 0.10s =========================
"""
    result = harvest_failures(stdout)
    assert result.total_failed == 2
    assert len(result.clusters) == 2
    assert all(cluster.signature.message_digest for cluster in result.clusters)


def test_harvest_parses_run_tests_wrapper_style() -> None:
    stdout = """
tests/test_gamma.py::test_three: AssertionError: boom
"""
    result = harvest_failures(stdout)
    assert result.total_failed == 1
    cluster = result.clusters[0]
    assert cluster.signature.test_name == "test_three"
    assert cluster.signature.error_type == "AssertionError"
