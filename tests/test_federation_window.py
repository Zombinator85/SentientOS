from datetime import datetime, timezone

from sentientos.federation.drift import DriftReport
from sentientos.federation.identity import NodeId
from sentientos.federation.window import build_window


def test_build_window_counts_and_flags() -> None:
    local = NodeId(name="local", fingerprint="abc123")
    now = datetime.now(timezone.utc)
    reports = {
        "peer-ok": DriftReport(peer="peer-ok", level="ok", reasons=["Aligned"]),
        "peer-warn": DriftReport(peer="peer-warn", level="warn", reasons=["Height mismatch"]),
        "peer-drift": DriftReport(peer="peer-drift", level="drift", reasons=["Diverged"]),
    }
    window = build_window(
        local,
        reports,
        now,
        expected_peer_count=4,
        max_drift_peers=1,
        max_incompatible_peers=0,
        max_missing_peers=0,
    )

    assert window.ok_count == 1
    assert window.warn_count == 1
    assert window.drift_count == 1
    assert window.incompatible_count == 0
    assert window.missing_count == 1
    assert window.is_quorum_healthy is True
    assert window.is_cluster_unstable is True


def test_single_node_defaults_to_healthy() -> None:
    local = NodeId(name="solo", fingerprint="fp")
    now = datetime.now(timezone.utc)
    window = build_window(local, {}, now)

    assert window.is_quorum_healthy is True
    assert window.is_cluster_unstable is False
    assert window.ok_count == 0
