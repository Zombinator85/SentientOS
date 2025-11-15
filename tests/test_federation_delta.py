from sentientos.federation.delta import compute_delta
from sentientos.federation.replay import (
    AmendmentReplay,
    ChainReplay,
    DreamReplay,
    ExperimentReplay,
    ReplayResult,
)


def _replay(
    *,
    amendments=None,
    experiments=None,
    chains=None,
    dream=None,
    persona="persona",
    runtime="cfg",
):
    return ReplayResult(
        identity="node",
        amendments=amendments
        or AmendmentReplay(
            last_applied_id="a",
            last_applied_digest="dg",
            ledger_height=5,
            rollback_count=0,
            applied_ids=("a1", "a2"),
            applied_digests=("d1", "d2"),
        ),
        experiments=experiments
        or ExperimentReplay(
            total=3,
            chains=1,
            dsl_version="1.0",
            run_totals=(("failed", 1), ("successful", 2), ("total", 3)),
            latest_ids=("exp-1",),
        ),
        chains=chains or ChainReplay(totals=(("total", 1),)),
        dream=dream or DreamReplay(fields=(("focus", "alignment"),), digest="dream"),
        persona_digest=persona,
        runtime_digest=runtime,
    )


def test_delta_low_severity_when_only_dream_differs():
    local = _replay()
    remote = _replay(dream=DreamReplay(fields=(("focus", "new"),), digest="other"))
    delta = compute_delta(local, remote)
    assert delta.severity == "low"
    assert delta.dream["reflection_divergence"] is True


def test_delta_medium_for_experiment_sequence_changes():
    local = _replay()
    remote = _replay(
        experiments=ExperimentReplay(
            total=4,
            chains=1,
            dsl_version="1.0",
            run_totals=(("failed", 2), ("successful", 2), ("total", 4)),
            latest_ids=("exp-2",),
        ),
    )
    delta = compute_delta(local, remote)
    assert delta.severity == "medium"
    assert "missing_experiments" in delta.experiment


def test_delta_high_for_runtime_digest_mismatch():
    local = _replay()
    remote = _replay(runtime="other")
    delta = compute_delta(local, remote)
    assert delta.severity == "high"
    assert "config_digest_mismatch" in delta.runtime


def test_delta_amendment_mismatch_detected():
    local = _replay()
    remote = _replay(
        amendments=AmendmentReplay(
            last_applied_id="a",
            last_applied_digest="dg",
            ledger_height=4,
            rollback_count=0,
            applied_ids=("a1",),
            applied_digests=("d1",),
        )
    )
    delta = compute_delta(local, remote)
    assert delta.severity == "high"
    assert delta.amendment["missing_amendments"] == ("a2",)
