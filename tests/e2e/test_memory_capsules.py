from sentientos.autonomy.runtime import MemoryCurator
from sentientos.config import ForgettingCurveConfig, MemoryCuratorConfig
from sentientos.metrics import MetricsRegistry


def test_memory_capsule_rollups():
    config = MemoryCuratorConfig(
        enable=True,
        rollup_interval_s=10,
        max_capsule_len=128,
        forgetting_curve=ForgettingCurveConfig(half_life_days=1.0, min_keep_score=0.5),
    )
    curator = MemoryCurator(config, MetricsRegistry())

    curator.ingest_turn("session", {"text": "first"}, importance=0.1, corr_id="c1")
    curator.ingest_turn("session", {"text": "second"}, importance=0.9, corr_id="c2")

    capsule = curator.rollup_session("session", "c3")
    assert capsule is not None
    assert capsule["turn_count"] == 2
    assert capsule["importance"] >= 1.0

    # The low-importance turn should be pruned by the forgetting curve
    assert curator.backlog() == 1
    status = curator.status()
    assert status["capsules"] == 1
