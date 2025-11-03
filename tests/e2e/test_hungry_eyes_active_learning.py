from sentientos.autonomy.runtime import HungryEyesActiveLearner
from sentientos.config import HungryEyesActiveLearningConfig
from sentientos.metrics import MetricsRegistry


def test_active_learning_triggers_retrain():
    config = HungryEyesActiveLearningConfig(
        enable=True,
        retrain_every_n_events=2,
        max_corpus_mb=1,
        seed=42,
    )
    metrics = MetricsRegistry()
    learner = HungryEyesActiveLearner(config, metrics)

    first = learner.observe({"status": "VIOLATION", "support": 5})
    assert not first["retrain"]

    second = learner.observe({"status": "VALID", "proof_report": {"valid": True}})
    assert second["retrain"]
    assert 0.0 <= second["risk"] <= 1.0

    snapshot = metrics.snapshot()
    assert "sos_hungryeyes_corpus_bytes" in snapshot["gauges"]

    status = learner.status()
    assert status["corpus_size"] >= 2
    assert status["last_retrain"]
