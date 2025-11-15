from dataclasses import replace
from datetime import datetime, timezone

from sentientos.federation.drift import compare_summaries
from sentientos.federation.summary import (
    CathedralIndexSnapshot,
    CathedralState,
    ConfigState,
    ExperimentIndexSnapshot,
    ExperimentState,
    FederationSummary,
    SummaryIndexes,
)


def _summary(node: str, ids, digest: str) -> FederationSummary:
    return FederationSummary(
        node_name=node,
        fingerprint=f"fp-{node}",
        ts=datetime.now(timezone.utc),
        cathedral=CathedralState(
            last_applied_id=ids[-1] if ids else "",
            last_applied_digest=digest,
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
                latest_ids=[f"exp-{node}"],
            ),
        ),
    )


def test_compare_summaries_adds_cathedral_reason_for_ahead() -> None:
    local = _summary("local", ["A1"], "dg-local")
    peer = _summary("peer", ["A1", "A2"], "dg-peer")
    report = compare_summaries(local, peer)
    assert report.level == "drift"
    assert "peer_ahead_cathedral" in report.reasons


def test_compare_summaries_adds_experiment_reason() -> None:
    local = _summary("local", ["A1"], "dg-local")
    peer = replace(
        _summary("peer", ["A1"], "dg-peer"),
        indexes=SummaryIndexes(
            cathedral=CathedralIndexSnapshot(applied_ids=["A1"], applied_digests=[], height=1),
            experiments=ExperimentIndexSnapshot(
                runs={"total": 1, "successful": 1, "failed": 0},
                chains={"total": 0, "completed": 0, "aborted": 0},
                latest_ids=["exp-new"],
            ),
        ),
    )
    report = compare_summaries(local, peer)
    assert "peer_ahead_experiments" in report.reasons


def test_compare_summaries_reports_divergent_history() -> None:
    local = _summary("local", ["A1", "A3"], "dg-local")
    peer = _summary("peer", ["A1", "A2"], "dg-peer")
    report = compare_summaries(local, peer)
    assert "cathedral_history_divergent" in report.reasons
