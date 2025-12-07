import pytest

from sentientos.consciousness.integration import integrity_summary


pytestmark = pytest.mark.no_legacy_skip


def test_integrity_summary_shape():
    summary = integrity_summary()

    assert "canonical_vow_digest" in summary
    assert "version_consensus" in summary
    assert "cycle_gate" in summary
    assert isinstance(summary["version_consensus"], dict)
