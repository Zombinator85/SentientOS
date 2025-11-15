from datetime import datetime, timezone

from sentientos.federation.drift import compare_summaries
from sentientos.federation.summary import CathedralState, ConfigState, ExperimentState, FederationSummary


def _summary(
    *,
    digest: str = "dg1",
    ledger: int = 5,
    config_digest: str = "cfg1",
    fingerprint: str = "fp1",
    dsl: str = "1.0",
    node: str = "local",
) -> FederationSummary:
    return FederationSummary(
        node_name=node,
        fingerprint=fingerprint,
        ts=datetime.now(timezone.utc),
        cathedral=CathedralState(
            last_applied_id="amend-1",
            last_applied_digest=digest,
            ledger_height=ledger,
            rollback_count=0,
        ),
        experiments=ExperimentState(total=1, chains=0, dsl_version=dsl),
        config=ConfigState(config_digest=config_digest),
        meta={},
    )


def test_compare_ok_state():
    local = _summary()
    peer = _summary(node="peer")
    report = compare_summaries(local, peer)
    assert report.level == "ok"
    assert "State aligned" in report.reasons


def test_compare_warn_height():
    local = _summary()
    peer = _summary(node="peer", ledger=7)
    report = compare_summaries(local, peer)
    assert report.level == "warn"
    assert any("Ledger height" in reason for reason in report.reasons)


def test_compare_drift_peer_ahead():
    local = _summary(digest="dg1", ledger=4)
    peer = _summary(node="peer", digest="dg2", ledger=6)
    report = compare_summaries(local, peer)
    assert report.level == "drift"
    assert any("Peer ledger height" in reason or "Peer ahead" in reason for reason in report.reasons)


def test_compare_incompatible_dsl():
    local = _summary(dsl="1.0")
    peer = _summary(node="peer", dsl="2.0")
    report = compare_summaries(local, peer)
    assert report.level == "incompatible"
    assert any("DSL" in reason for reason in report.reasons)
