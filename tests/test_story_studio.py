"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import story_studio
import replay


def test_load_and_save(tmp_path):
    sb = tmp_path / "sb.json"
    data = {"chapters": [{"chapter": 1, "text": "a"}]}
    story_studio.save_storyboard(data, sb)
    loaded = story_studio.load_storyboard(sb)
    assert loaded == data


def test_reorder(tmp_path):
    chapters = [{"chapter": 1}, {"chapter": 2}, {"chapter": 3}]
    new = story_studio.reorder_chapters(chapters, [3, 1, 2])
    assert [c["chapter"] for c in new] == [1, 2, 3]


def test_timeline_output(tmp_path, capsys):
    sb = tmp_path / "sb.json"
    data = {"chapters": [
        {"chapter": 1, "t_start": 0, "mood": "happy", "voice": "A"},
        {"chapter": 2, "t_start": 10, "mood": "sad", "voice": "B", "highlight": True}
    ]}
    sb.write_text(json.dumps(data))
    replay.print_timeline(str(sb))
    out = capsys.readouterr().out
    assert "happy" in out and "sad" in out

