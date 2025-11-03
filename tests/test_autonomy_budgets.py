from sentientos.autonomy import AutonomyRuntime
from sentientos.config import load_runtime_config
from sentientos.metrics import MetricsRegistry


def build_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    config = load_runtime_config()
    config.reflexion.enable = True
    config.critic.enable = True
    config.critic.factcheck.enable = True
    config.council.enable = True
    config.council.quorum = 2
    config.oracle.enable = True
    config.goals.curator.enable = True
    config.goals.curator.min_support_count = 1
    config.goals.curator.min_days_between_auto_goals = 0.0
    config.goals.curator.max_concurrent_auto_goals = 2
    config.budgets.reflexion.max_per_hour = 1
    config.budgets.oracle.max_requests_per_day = 1
    config.budgets.goals.max_autocreated_per_day = 1
    runtime = AutonomyRuntime(config, metrics=MetricsRegistry())
    return runtime


def test_reflexion_budget_limits(monkeypatch, tmp_path):
    runtime = build_runtime(tmp_path, monkeypatch)
    assert runtime.reflexion.run("first", corr_id="a") is not None
    assert runtime.reflexion.run("second", corr_id="b") is None
    status = runtime.reflexion.status()
    assert status["status"] == "limited"
    assert status["budget_remaining"] == 0


def test_oracle_budget_limits(monkeypatch, tmp_path):
    runtime = build_runtime(tmp_path, monkeypatch)

    assert runtime.oracle.execute(lambda: {"ok": True}, corr_id="1")["mode"] == "online"
    limited = runtime.oracle.execute(lambda: {"ok": True}, corr_id="2")
    assert limited["error"] == "rate_limited"
    status = runtime.oracle.status()
    assert status["status"] == "degraded"
    assert status["budget_remaining"] == 0


def test_goal_budget_limits(monkeypatch, tmp_path):
    runtime = build_runtime(tmp_path, monkeypatch)
    created_first = runtime.goal_curator.consider({"title": "one"}, corr_id="1", support_count=1)
    created_second = runtime.goal_curator.consider({"title": "two"}, corr_id="2", support_count=1)
    assert created_first is True
    assert created_second is False
    status = runtime.goal_curator.status()
    assert status["status"] == "limited"
    assert status["budget_remaining"] == 0
