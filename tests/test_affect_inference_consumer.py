from __future__ import annotations

import json
from pathlib import Path

from scripts.perception.affect_inference_consumer import run


def test_affect_inference_off_by_default(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "perception.jsonl"
    src.write_text("", encoding="utf-8")
    out = tmp_path / "affect.jsonl"
    monkeypatch.delenv("ENABLE_AFFECT_INFERENCE", raising=False)
    rc = run(input_path=src, output_path=out)
    assert rc == 0
    assert not out.exists()


def test_affect_inference_emits_expression_only_payload(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "perception.jsonl"
    event = {
        "payload": {
            "event_type": "perception.audio",
            "confidence": 0.8,
            "features": {"rms_energy": 0.4, "speech_prob": 0.5},
        }
    }
    src.write_text(json.dumps(event) + "\n", encoding="utf-8")
    out = tmp_path / "affect.jsonl"
    monkeypatch.setenv("ENABLE_AFFECT_INFERENCE", "1")

    rc = run(input_path=src, output_path=out)
    assert rc == 0

    row = json.loads(out.read_text(encoding="utf-8").strip())
    assert row["event_type"] == "affect.telemetry"
    assert row["mode"] == "expression_only"
    assert row["action_selection_influence"] is False
    assert row["bounded_influence"] == "phrasing_telemetry_only"
