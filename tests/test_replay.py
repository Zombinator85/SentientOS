import os
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import replay


def test_replay_cli(tmp_path, capsys, monkeypatch):
    sb = tmp_path / "sb.json"
    sb.write_text(json.dumps({"chapters": [{"chapter": 1, "title": "A", "audio": "a.mp3", "text": "hi"}]}))
    monkeypatch.setattr(sys, "argv", ["rp", "--storyboard", str(sb), "--headless"])
    replay.main()
    out = capsys.readouterr().out
    assert "Chapter 1" in out


def test_avatar_callback(tmp_path, monkeypatch):
    sb = tmp_path / "sb.json"
    sb.write_text(json.dumps({"chapters": [{"chapter": 1, "title": "A", "text": "hi", "mood": "calm", "persona": "Lumos", "t_start": 0, "t_end": 0.1}]}))
    calls = []
    def fake_run(cmd, shell=True, check=False):
        calls.append(cmd)
    monkeypatch.setattr(replay.subprocess, "run", fake_run)
    replay.playback(str(sb), headless=True, avatar_callback="echo avatar", show_subtitles=False)
    assert calls and "--emotion=calm" in calls[0]


def test_subtitles_progress_and_jump(tmp_path, capsys, monkeypatch):
    sb = tmp_path / "sb.json"
    sb.write_text(json.dumps({"chapters": [
        {"chapter": 1, "title": "A", "text": "hi", "t_start": 0, "t_end": 0.1},
        {"chapter": 2, "title": "B", "text": "bye", "t_start": 0.1, "t_end": 0.2}
    ]}))
    monkeypatch.setattr(time, "sleep", lambda x: None)
    replay.playback(str(sb), headless=True, show_subtitles=True, start_chapter=2)
    out = capsys.readouterr().out
    assert "Chapter 2" in out and "bye" in out and "100%" in out


def test_image_display(tmp_path, capsys):
    sb = tmp_path / "sb.json"
    img = tmp_path / "img.png"
    img.write_text("img")
    sb.write_text(json.dumps({"chapters": [{"chapter": 1, "title": "A", "image": str(img), "t_start": 0, "t_end": 0.1}]}))
    replay.playback(str(sb), headless=False, gui=True, audio_only=True)
    out = capsys.readouterr().out
    assert "[IMAGE]" in out


def test_reaction_hooks(tmp_path, monkeypatch):
    sb = tmp_path / "sb.json"
    sb.write_text(json.dumps({
        "chapters": [{
            "chapter": 1,
            "title": "A",
            "text": "hi",
            "sfx": "ding.wav",
            "gesture": "wave",
            "env": "flash",
            "t_start": 0,
            "t_end": 0.1
        }]
    }))
    calls = []
    monkeypatch.setattr(replay, "_trigger_sfx", lambda s: calls.append(("sfx", s)))
    monkeypatch.setattr(replay, "_trigger_gesture", lambda g: calls.append(("gesture", g)))
    monkeypatch.setattr(replay, "_trigger_env", lambda e: calls.append(("env", e)))
    monkeypatch.setattr(time, "sleep", lambda x: None)
    replay.playback(str(sb), headless=True, enable_gestures=True, enable_sfx=True, enable_env=True)
    assert ("sfx", "ding.wav") in calls and ("gesture", "wave") in calls and ("env", "flash") in calls


def test_emotion_overlay(tmp_path, capsys, monkeypatch):
    sb = tmp_path / "sb.json"
    sb.write_text(json.dumps({"chapters": [{"chapter": 1, "title": "A", "mood": "joy", "t_start": 0, "t_end": 0.1}]}))
    monkeypatch.setattr(time, "sleep", lambda x: None)
    replay.playback(str(sb), headless=True)
    out = capsys.readouterr().out
    assert "Emotion: joy" in out


def test_highlight_only(tmp_path, capsys, monkeypatch):
    sb = tmp_path / "sb.json"
    sb.write_text(json.dumps({"chapters": [
        {"chapter": 1, "title": "A", "text": "one", "highlight": False, "t_start": 0, "t_end": 0.1},
        {"chapter": 2, "title": "B", "text": "two", "highlight": True, "t_start": 0.1, "t_end": 0.2}
    ]}))
    monkeypatch.setattr(time, "sleep", lambda x: None)
    replay.playback(str(sb), headless=True, highlights_only=True)
    out = capsys.readouterr().out
    assert "Chapter 1" not in out and "Chapter 2" in out

