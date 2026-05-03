from __future__ import annotations

import json

from sentientos import dashboard_api, ritual_api


def test_ritual_api_round_trip_preserves_record_shape(tmp_path, monkeypatch) -> None:
    att_path = tmp_path / "att.jsonl"
    rel_path = tmp_path / "rel.jsonl"
    monkeypatch.setattr("attestation.LOG_PATH", att_path)
    monkeypatch.setattr("relationship_log.LOG_PATH", rel_path)

    event_id = ritual_api.add_attestation("evt-1", "tester", comment="ok", quote="q")
    assert event_id

    att = ritual_api.ritual_attestations_history("evt-1", limit=5)
    assert att and att[-1]["event"] == "evt-1"
    assert set(["id", "timestamp", "event", "user", "comment", "quote"]).issubset(att[-1].keys())


def test_dashboard_api_mood_blessing_delegates_to_canonical_shape(monkeypatch) -> None:
    captured = {}

    def _fake(user, scope, emotion, phrase):
        captured.update({"user": user, "scope": scope, "emotion": emotion, "phrase": phrase})
        return {"status": "ok"}

    monkeypatch.setattr("ledger.log_mood_blessing", _fake)
    out = dashboard_api.log_mood_blessing("u", "joy", "u blesses joy")
    assert out == {"status": "ok"}
    assert captured == {
        "user": "u",
        "scope": "public",
        "emotion": {"joy": 1.0},
        "phrase": "u blesses joy",
    }
