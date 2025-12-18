import json

from sentientos.ethics import SymbolicHygieneMonitor


def test_symbolic_hygiene_monitor_flags_slippage(tmp_path):
    monitor = SymbolicHygieneMonitor(tmp_path)
    glossary = {"forbidden": ["cathedral"], "deprecated": ["heresy"]}
    logs = [
        "We keep the cathedral references sealed.",
        "Stories repeat the Cathedral echo.",
    ]
    fragments = ["A hint of heresy returns in whispers."]

    result = monitor.evaluate(glossary, logs, fragments=fragments, threshold=0.1)

    assert result["covenant_notice"] is True
    assert result["hygiene_score"] < 0.9

    saved = (tmp_path / "symbolic_hygiene_alerts.jsonl").read_text().strip().splitlines()
    payload = json.loads(saved[-1])
    assert any(v["term"] == "cathedral" for v in payload["violations"])
    assert any(v["term"] == "heresy" for v in payload["violations"])
