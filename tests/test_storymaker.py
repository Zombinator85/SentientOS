import os
import sys
import json
import datetime as dt
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import storymaker
import tts_bridge


def test_storymaker_dry_run(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "memory.jsonl").write_text(json.dumps({"timestamp": "2024-01-01T10:00:00", "text": "boot"}) + "\n")
    (log_dir / "reflection.jsonl").write_text(json.dumps({"timestamp": "2024-01-01T12:00:00", "text": "ok"}) + "\n")
    (log_dir / "emotions.jsonl").write_text(json.dumps({"timestamp": "2024-01-01T11:00:00", "emotions": {"Joy": 1.0}}) + "\n")

    def fake_speak(text, voice=None, save_path=None, emotions=None):
        path = save_path or str(tmp_path / "aud.mp3")
        Path(path).write_text("audio")
        return path

    monkeypatch.setattr(tts_bridge, "speak", fake_speak)

    narrative, audio, video = storymaker.run_pipeline(
        "2024-01-01 00:00", "2024-01-01 23:59", str(tmp_path / "demo.mp4"), log_dir, dry_run=True
    )
    assert "boot" in narrative
    assert audio and Path(audio).exists()
    assert video is None


def test_storymaker_cli(tmp_path, monkeypatch, capsys):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "memory.jsonl").write_text(json.dumps({"timestamp": "2024-01-01T08:00:00", "text": "start"}) + "\n")
    (log_dir / "reflection.jsonl").write_text(json.dumps({"timestamp": "2024-01-01T09:00:00", "text": "done"}) + "\n")
    (log_dir / "emotions.jsonl").write_text(json.dumps({"timestamp": "2024-01-01T08:30:00", "emotions": {"Joy": 0.9}}) + "\n")

    monkeypatch.setattr(tts_bridge, "speak", lambda *a, **k: str(tmp_path / "a.mp3"))
    monkeypatch.setattr(sys, "argv", [
        "sm", "--from", "2024-01-01 00:00", "--to", "2024-01-01 23:59",
        "--output", str(tmp_path / "demo.mp4"), "--log-dir", str(log_dir), "--dry-run"
    ])
    storymaker.main()
    out = capsys.readouterr().out
    assert "start" in out


def test_chapter_segmentation(tmp_path):
    mem = [
        {"timestamp": "2024-01-01T10:00:00", "text": "A"},
        {"timestamp": "2024-01-01T12:30:00", "text": "B"},
    ]
    chapters = storymaker.segment_chapters(mem, [], [])
    assert len(chapters) == 2


def test_subtitle_generation(tmp_path):
    ch = storymaker.Chapter(
        start=dt.datetime(2024, 1, 1, 10, 0),
        end=dt.datetime(2024, 1, 1, 10, 5),
        memory=[],
        reflection=[],
        emotions=[],
        text="hello world",
    )
    path = tmp_path / "out.srt"
    storymaker.write_srt([ch], path)
    data = path.read_text()
    assert "1" in data and "-->" in data and "hello world" in data


def test_storyboard_flag(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "memory.jsonl").write_text(json.dumps({"timestamp": "2024-01-01T08:00:00", "text": "start"}) + "\n")
    monkeypatch.setattr(tts_bridge, "speak", lambda *a, **k: str(tmp_path / "a.mp3"))
    sb = tmp_path / "sb.json"
    storymaker.run_pipeline(
        "2024-01-01 00:00", "2024-01-01 23:59", str(tmp_path / "demo.mp4"), log_dir,
        dry_run=True, chapters=True, storyboard=str(sb)
    )
    data = json.loads(sb.read_text())
    assert data["chapters"]


def test_emotion_and_sync_metadata(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "memory.jsonl").write_text(json.dumps({"timestamp": "2024-01-01T08:00:00", "text": "start"}) + "\n")
    (log_dir / "emotions.jsonl").write_text(json.dumps({"timestamp": "2024-01-01T08:30:00", "emotions": {"Joy": 0.9}, "features": {"valence": 0.8, "arousal": 0.6}}) + "\n")
    monkeypatch.setattr(tts_bridge, "speak", lambda *a, **k: str(tmp_path / "a.mp3"))
    emo_path = tmp_path / "emo.json"
    sync_path = tmp_path / "sync.json"
    storymaker.run_pipeline(
        "2024-01-01 00:00", "2024-01-01 23:59", str(tmp_path / "demo.mp4"), log_dir,
        dry_run=True, chapters=True, emotion_data=str(emo_path), sync_metadata=str(sync_path)
    )
    assert json.loads(emo_path.read_text())["chapters"]
    assert json.loads(sync_path.read_text())[0]["start"] == 0


def test_scene_image_generation(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "memory.jsonl").write_text(json.dumps({"timestamp": "2024-01-01T08:00:00", "text": "start"}) + "\n")
    monkeypatch.setattr(tts_bridge, "speak", lambda *a, **k: str(tmp_path / "a.mp3"))
    storymaker.run_pipeline(
        "2024-01-01 00:00", "2024-01-01 23:59", str(tmp_path / "demo.mp4"), log_dir,
        dry_run=True, chapters=True, scene_images=True
    )
    assert (tmp_path / "chapter_1.png").exists()

