import os
import sys
import json
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
