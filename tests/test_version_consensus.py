import pytest

from version_consensus import VersionConsensus

pytestmark = pytest.mark.no_legacy_skip


def test_compare_match():
    local = "abc"
    vc = VersionConsensus(local)
    result = vc.compare("abc")
    assert result == {
        "match": True,
        "local_digest": local,
        "peer_digest": "abc",
    }


def test_compare_mismatch_and_is_compatible():
    local = "abc"
    peer = "xyz"
    vc = VersionConsensus(local)
    comparison = vc.compare(peer)
    assert comparison == {
        "match": False,
        "local_digest": local,
        "peer_digest": peer,
    }
    assert not vc.is_compatible(peer)
    assert vc.is_compatible(local)


def test_drift_report():
    vc = VersionConsensus("local")

    report = vc.drift_report("expected")

    assert report == {
        "local_digest": "local",
        "expected_digest": "expected",
        "match": False,
        "status": "drift_detected",
    }


def test_summary_always_passive():
    vc = VersionConsensus("canonical")

    summary = vc.summary()

    assert summary == {
        "canonical_digest": "canonical",
        "ready_for_network_use": False,
    }
    assert summary["ready_for_network_use"] is False
