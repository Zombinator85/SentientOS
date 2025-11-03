from sentientos.autonomy.runtime import GoalCurator
from sentientos.config import GoalsCuratorConfig
from sentientos.metrics import MetricsRegistry


def test_goal_curator_throttle():
    config = GoalsCuratorConfig(
        enable=True,
        min_support_count=2,
        min_days_between_auto_goals=1.0,
        max_concurrent_auto_goals=2,
    )
    curator = GoalCurator(config, MetricsRegistry())

    assert curator.consider({"title": "A"}, corr_id="1", support_count=3, now=0.0)
    # Too soon based on min_days
    assert not curator.consider({"title": "B"}, corr_id="2", support_count=3, now=1000.0)
    # Enough time elapsed
    assert curator.consider({"title": "C"}, corr_id="3", support_count=3, now=90000.0)
    # Support below threshold
    assert not curator.consider({"title": "D"}, corr_id="4", support_count=1, now=200000.0)

    status = curator.status()
    assert status["active"] <= config.max_concurrent_auto_goals
    assert status["tokens"] <= config.max_concurrent_auto_goals
