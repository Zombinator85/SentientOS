from datetime import datetime, timezone

from sentientos.federation.summary import (
    CathedralIndexSnapshot,
    CathedralState,
    ConfigState,
    ExperimentIndexSnapshot,
    ExperimentState,
    FederationSummary,
    SummaryIndexes,
)
from sentientos.federation.sync_view import build_peer_sync_view, compute_cathedral_sync, compute_experiment_sync


def _summary(ids, latest_experiments):
    return FederationSummary(
        node_name="node",
        fingerprint="fp",
        ts=datetime.now(timezone.utc),
        cathedral=CathedralState(
            last_applied_id=ids[-1] if ids else "",
            last_applied_digest="dg",
            ledger_height=len(ids),
            rollback_count=0,
        ),
        experiments=ExperimentState(total=0, chains=0, dsl_version="1.0"),
        config=ConfigState(config_digest="cfg"),
        meta={},
        indexes=SummaryIndexes(
            cathedral=CathedralIndexSnapshot(applied_ids=ids, applied_digests=[], height=len(ids)),
            experiments=ExperimentIndexSnapshot(
                runs={"total": 0, "successful": 0, "failed": 0},
                chains={"total": 0, "completed": 0, "aborted": 0},
                latest_ids=latest_experiments,
            ),
        ),
    )


def test_compute_cathedral_sync_peer_ahead() -> None:
    view = compute_cathedral_sync(["A1"], ["A1", "A2"])
    assert view.status == "ahead_of_me"
    assert view.missing_local_ids == ["A2"]


def test_compute_cathedral_sync_divergent_detects_missing_both() -> None:
    view = compute_cathedral_sync(["A1", "A3"], ["A1", "A2"])
    assert view.status == "divergent"
    assert view.missing_local_ids == ["A2"]
    assert view.missing_peer_ids == ["A3"]


def test_compute_experiment_sync_unknown_when_empty() -> None:
    view = compute_experiment_sync([], [])
    assert view.status == "unknown"


def test_build_peer_sync_handles_missing_indexes() -> None:
    local = _summary(["A1"], ["exp-1"])
    peer = FederationSummary(
        node_name="peer",
        fingerprint="fp-peer",
        ts=datetime.now(timezone.utc),
        cathedral=local.cathedral,
        experiments=local.experiments,
        config=local.config,
        meta={},
        indexes=None,
    )
    view = build_peer_sync_view(local, peer)
    assert view.cathedral.status == "unknown"
    assert "peer_no_index" in view.cathedral.reasons


def test_build_peer_sync_marks_experiments_only() -> None:
    local = _summary(["A1", "A2"], ["exp-1"])
    peer = _summary(["A1", "A2"], ["exp-1", "exp-2"])
    view = build_peer_sync_view(local, peer)
    assert view.cathedral.status == "aligned"
    assert view.experiments.status == "ahead_of_me"
    assert "experiments_only" in view.experiments.reasons
