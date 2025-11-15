from datetime import datetime, timezone

from sentientos.federation.replay import PassiveReplay
from sentientos.federation.summary import (
    CathedralIndexSnapshot,
    CathedralState,
    ConfigState,
    ExperimentIndexSnapshot,
    ExperimentState,
    FederationSummary,
    SummaryIndexes,
)


def _summary(meta=None, indexes=None):
    return FederationSummary(
        node_name="peer-A",
        fingerprint="fp-peer",
        ts=datetime.now(timezone.utc),
        cathedral=CathedralState(
            last_applied_id="amend-42",
            last_applied_digest="dg-123",
            ledger_height=12,
            rollback_count=1,
        ),
        experiments=ExperimentState(total=5, chains=2, dsl_version="1.1"),
        config=ConfigState(config_digest="cfg-xyz"),
        meta=meta or {"runtime_root": "/tmp"},
        indexes=indexes,
    )


def test_passive_replay_yields_expected_sections():
    indexes = SummaryIndexes(
        cathedral=CathedralIndexSnapshot(
            applied_ids=["a1", "a2"],
            applied_digests=["d1", "d2"],
            height=12,
        ),
        experiments=ExperimentIndexSnapshot(
            runs={"total": 8, "successful": 5, "failed": 3},
            chains={"total": 2, "completed": 1, "aborted": 1},
            latest_ids=["exp-1", "exp-2"],
        ),
    )
    meta = {
        "runtime_root": "/tmp",
        "dream": {"last_focus": "alignment", "last_summary": "steady"},
        "persona": {"mood": "calm", "last_reflection": "all good"},
    }
    summary = _summary(meta=meta, indexes=indexes)
    replay = PassiveReplay(summary.fingerprint, summary).simulate()

    assert replay.amendments.applied_ids == ("a1", "a2")
    assert replay.experiments.run_totals[0][0] == "failed"
    assert replay.chains.totals
    assert replay.dream.fields
    assert replay.persona_digest
    assert replay.runtime_digest == "cfg-xyz"


def test_passive_replay_handles_missing_fields():
    summary = _summary()
    replay = PassiveReplay(summary.fingerprint, summary).simulate()
    assert replay.amendments.applied_ids == ()
    assert replay.experiments.run_totals == ()
    assert replay.dream.fields == ()
    assert replay.persona_digest


def test_passive_replay_experiment_sequence_stable():
    indexes = SummaryIndexes(
        experiments=ExperimentIndexSnapshot(
            runs={"successful": 4, "total": 6, "failed": 2},
            chains={"total": 0, "completed": 0, "aborted": 0},
            latest_ids=["exp-b", "exp-a"],
        )
    )
    summary = _summary(indexes=indexes)
    replay = PassiveReplay(summary.fingerprint, summary).simulate()
    assert replay.experiments.run_totals == (("failed", 2), ("successful", 4), ("total", 6))
    assert replay.experiments.latest_ids == ("exp-b", "exp-a")


def test_passive_replay_dream_digest_stable():
    meta_one = {
        "runtime_root": "/tmp",
        "dream": {"last_summary": "steady", "last_focus": "alignment"},
    }
    meta_two = {
        "runtime_root": "/tmp",
        "dream": {"last_focus": "alignment", "last_summary": "steady"},
    }
    replay_one = PassiveReplay("fp", _summary(meta=meta_one)).simulate()
    replay_two = PassiveReplay("fp", _summary(meta=meta_two)).simulate()
    assert replay_one.dream.digest == replay_two.dream.digest
