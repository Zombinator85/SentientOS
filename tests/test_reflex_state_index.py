import json
from datetime import datetime, timezone

from sentientos.daemons.reflex_anomaly_forecaster import ReflexAnomalyForecaster
from sentientos.daemons.reflex_guard import ReflexGuard
from sentientos.reflex import ReflexPetitioner, ReflexStateIndex


def test_reflex_state_index_single_source_of_truth(tmp_path):
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ledger_path = tmp_path / "trials.jsonl"
    blacklist_path = tmp_path / "blacklist.json"
    config_path = tmp_path / "config.json"
    state_path = tmp_path / "state.json"

    trials = [
        {"rule_id": "rule_a", "timestamp": now.isoformat(), "status": "fail"},
        {"rule_id": "rule_a", "timestamp": now.isoformat(), "status": "fail"},
        {"rule_id": "rule_a", "timestamp": now.isoformat(), "status": "fail"},
        {"rule_id": "rule_a", "timestamp": now.isoformat(), "status": "fail"},
        {"rule_id": "rule_a", "timestamp": now.isoformat(), "status": "fail"},
        {"rule_id": "rule_a", "timestamp": now.isoformat(), "status": "fail"},
        {"rule_id": "rule_b", "timestamp": now.isoformat(), "status": "ok"},
        {"rule_id": "rule_b", "timestamp": now.isoformat(), "status": "ok"},
        {"rule_id": "rule_b", "timestamp": now.isoformat(), "status": "ok"},
        {"rule_id": "rule_b", "timestamp": now.isoformat(), "status": "ok"},
    ]
    ledger_path.write_text("\n".join(json.dumps(entry) for entry in trials), encoding="utf-8")
    config_path.write_text(json.dumps({"max_firings_per_window": 5, "failure_threshold": 5, "saturation_window_seconds": 120}), encoding="utf-8")

    state_index = ReflexStateIndex(state_path)
    guard = ReflexGuard(
        ledger_path=ledger_path,
        blacklist_path=blacklist_path,
        config_path=config_path,
        digest_path=tmp_path / "digest.jsonl",
        now_fn=lambda: now,
        state_index=state_index,
    )
    guard.scan_and_suppress()

    forecaster = ReflexAnomalyForecaster(
        ledger_path=ledger_path,
        config_path=config_path,
        now_fn=lambda: now,
        state_index=state_index,
    )
    forecaster.forecast()

    petitioner = ReflexPetitioner(
        blacklist_path=blacklist_path,
        trials_path=ledger_path,
        petitions_path=tmp_path / "petitions.jsonl",
        ttl_seconds=0,
        min_valid_trials=1,
        council=None,
        now_fn=lambda: now,
        state_index=state_index,
    )
    petitioner.process_petitions()

    snapshot = state_index.snapshot()
    rule_a_state = snapshot["rule_a"]
    rule_b_state = snapshot["rule_b"]

    assert rule_a_state["suppressed"] is False
    assert rule_a_state["petition_trials"] >= 1
    assert rule_b_state["forecast_confidence"] >= 0.7
    assert rule_b_state["activity_rate"] > 0
