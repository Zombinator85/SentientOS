import json
from sentientos.analysis import PatternVolatilityScanner


def test_pattern_volatility_spike_triggers_alert(tmp_path):
    scanner = PatternVolatilityScanner(tmp_path)
    baseline = [{"reflex": "reflex-alpha"}, {"reflex": "reflex-alpha"}]
    current = [{"reflex": "reflex-alpha"} for _ in range(8)]

    alerts = scanner.scan(current, baseline=baseline, threshold_ratio=3.0)

    assert alerts and alerts[0]["reflex"] == "reflex-alpha"
    assert alerts[0]["ratio"] >= 4

    saved = (tmp_path / "integration_anomalies.jsonl").read_text().strip().splitlines()
    payload = json.loads(saved[-1])
    assert payload["instability_risk"] > 0
    assert payload["events_seen"] == 8
