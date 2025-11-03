import json
from pathlib import Path

import pytest

from sentientos.autonomy import AutonomyRuntime, OracleMode, run_rehearsal
from sentientos.config import load_runtime_config
from sentientos.metrics import MetricsRegistry


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    config = load_runtime_config()
    config.memory.curator.enable = True
    config.reflexion.enable = True
    config.critic.enable = True
    config.critic.factcheck.enable = True
    config.council.enable = True
    config.council.quorum = 2
    config.oracle.enable = True
    config.oracle.timeout_s = 0.01
    config.goals.curator.enable = True
    config.goals.curator.min_support_count = 1
    config.goals.curator.min_days_between_auto_goals = 0.1
    config.goals.curator.max_concurrent_auto_goals = 2
    config.hungry_eyes.active_learning.enable = True
    config.hungry_eyes.active_learning.retrain_every_n_events = 1
    config.hungry_eyes.active_learning.max_corpus_mb = 1
    return AutonomyRuntime(config, metrics=MetricsRegistry())


def test_rehearsal_flow(runtime, tmp_path):
    def oracle_ok(_index: int) -> dict[str, object]:
        return {"status": "ok"}

    def oracle_timeout(_index: int) -> dict[str, object]:
        raise TimeoutError("oracle offline")

    result = run_rehearsal(
        cycles=2,
        runtime=runtime,
        oracle_plan=[oracle_ok, oracle_timeout],
        critic_plan=[{}, {"disagreement": True, "reason": "fact mismatch"}],
    )

    assert runtime.oracle.mode == OracleMode.DEGRADED
    assert result["peer_reviews"], "peer review trail expected when critic disagrees"

    data_root = Path(tmp_path)
    report_path = data_root / "glow" / "rehearsal" / "latest" / "REHEARSAL_REPORT.json"
    integrity_path = data_root / "glow" / "rehearsal" / "latest" / "INTEGRITY_SUMMARY.json"
    log_path = data_root / "glow" / "rehearsal" / "latest" / "logs" / "runtime.jsonl"
    metrics_path = data_root / "glow" / "rehearsal" / "latest" / "metrics.snap"

    for path in (report_path, integrity_path, log_path, metrics_path):
        assert path.exists(), f"expected artifact {path}"

    payload = json.loads(report_path.read_text())
    assert payload["payload"]["oracle_mode"] == OracleMode.DEGRADED.value
    assert "signature" in payload

    with log_path.open("r", encoding="utf-8") as handle:
        entries = [json.loads(line) for line in handle if line.strip()]
    assert any(not entry["council"]["quorum"] for entry in entries) or any(
        entry["council"]["outcome"] != "tied" for entry in entries
    )

    metrics = json.loads(metrics_path.read_text())
    assert metrics["counters"].get("sos_critic_disagreements_total", 0) >= 1
