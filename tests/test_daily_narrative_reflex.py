from __future__ import annotations

import json
from datetime import date, datetime, timezone

import daily_narrative_reflex as reflex_module


def _write_jsonl(path, entries) -> None:
    lines = [json.dumps(entry) for entry in entries]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_daily_narrative_generation(tmp_path, monkeypatch) -> None:
    digests_dir = tmp_path / "digests"
    digests_dir.mkdir()
    monkeypatch.setattr(reflex_module, "DIGEST_DIR", digests_dir, raising=False)

    now = datetime.now(timezone.utc).isoformat()
    perception_path = tmp_path / "perception.jsonl"
    curiosity_path = tmp_path / "curiosity.jsonl"
    transcripts_path = tmp_path / "conversations.jsonl"
    mood_path = tmp_path / "mood.jsonl"

    monkeypatch.setattr(reflex_module.memory_manager, "OBSERVATION_LOG_PATH", perception_path, raising=False)
    monkeypatch.setattr(reflex_module.memory_manager, "CURIOSITY_REFLECTIONS_PATH", curiosity_path, raising=False)
    monkeypatch.setattr(reflex_module.memory_manager, "TRANSCRIPT_LOG_PATH", transcripts_path, raising=False)
    monkeypatch.setattr(reflex_module, "MOOD_LOG", str(mood_path), raising=False)

    _write_jsonl(perception_path, [{"timestamp": now, "summary": "Saw sunrise"}])
    _write_jsonl(curiosity_path, [{"timestamp": now, "idea": "Experiment"}])
    _write_jsonl(transcripts_path, [{"timestamp": now, "text": "Hello"}])
    _write_jsonl(mood_path, [{"timestamp": now, "mood": {"joyful": 0.8}}])

    highlights = [{"text": "Completed onboarding"}]
    monkeypatch.setattr(reflex_module.memory_manager, "search_by_tags", lambda tags, limit=5: highlights)

    captured = {}

    def fake_append_memory(text: str, **kwargs) -> None:
        captured["memory_text"] = text
        captured["tags"] = kwargs.get("tags")

    monkeypatch.setattr(reflex_module.memory_manager, "append_memory", fake_append_memory)

    reflex = reflex_module.DailyNarrativeReflex(
        llm=lambda ctx: "Summary text with highlights.",
        speak=lambda text: captured.setdefault("spoken", text),
    )

    digest_path = reflex.run(day=date(2024, 1, 2), speak=True)
    assert digest_path.exists()
    content = digest_path.read_text(encoding="utf-8")
    assert "Summary text with highlights." in content
    assert captured["tags"] == ["daily_digest"]
    assert captured["spoken"] == "Summary text with highlights."

    latest = reflex.read_latest()
    assert latest is not None
    assert "Summary text with highlights." in latest

