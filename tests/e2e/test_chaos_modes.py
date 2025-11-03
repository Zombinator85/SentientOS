import argparse
import importlib
from pathlib import Path

import pytest
from textwrap import dedent


def write_config(path: Path) -> None:
    config = dedent(
        """
        memory:
          curator:
            enable: true
        reflexion:
          enable: true
        critic:
          enable: true
          factcheck:
            enable: true
        council:
          enable: true
          quorum: 2
          tie_breaker: chair
        oracle:
          enable: true
          timeout_s: 0.01
        goals:
          curator:
            enable: true
            min_support_count: 1
            min_days_between_auto_goals: 0.0
            max_concurrent_auto_goals: 3
        hungry_eyes:
          active_learning:
            enable: true
            retrain_every_n_events: 1
            max_corpus_mb: 1
        budgets:
          reflexion:
            max_per_hour: 2
          oracle:
            max_requests_per_day: 2
          goals:
            max_autocreated_per_day: 2
        """
    )
    path.write_text(config, encoding="utf-8")


@pytest.fixture()
def admin_runtime(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    write_config(config_path)
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SENTIENTOS_CONFIG", str(config_path))
    import sentientos.admin_server as admin_server

    admin_server = importlib.reload(admin_server)
    return admin_server


def test_chaos_modes_cover_degradation(admin_runtime):
    import sentientos.chaos as chaos

    chaos = importlib.reload(chaos)

    oracle = chaos.oracle_drop()
    assert oracle["status"]["mode"] == "degraded"

    critic = chaos.critic_lag()
    assert any(review.get("timed_out") for review in critic["reviews"])

    council = chaos.council_split()
    assert council["split"]["outcome"] in {"approved", "rejected"}
    assert council["split"]["notes"].startswith("tie_breaker")

    curator = chaos.curator_burst(5)
    assert curator.get("backlog", 0) >= 5

    payload = chaos.handle(
        argparse.Namespace(
            oracle_drop=False,
            critic_lag=False,
            council_split=False,
            curator_burst=0,
        )
    )
    assert payload["status"]["modules"]["oracle"]["mode"] in {"online", "degraded"}
    assert "sos" in payload["metrics"]


def test_alert_snapshot_generates_files(admin_runtime, tmp_path):
    import sentientos.alerts as alerts

    alerts = importlib.reload(alerts)
    snapshot = alerts.snapshot()
    paths = snapshot["paths"]
    assert paths
    for prom_path in paths.values():
        assert Path(prom_path).exists()
        content = Path(prom_path).read_text(encoding="utf-8")
        assert "sentientos_alert" in content
