"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import importlib
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import neos_lorebook_writer as nlw


def setup_logs(tmp_path):
    origin = tmp_path / "origin.jsonl"
    ceremony = tmp_path / "ceremony.jsonl"
    teach = tmp_path / "teach.jsonl"
    council = tmp_path / "council.jsonl"
    for p in (origin, ceremony, teach, council):
        p.write_text("{}\n")
    return origin, ceremony, teach, council


def test_compile_and_gallery(tmp_path, monkeypatch, capsys):
    origin, ceremony, teach, council = setup_logs(tmp_path)
    out = tmp_path / "out.json"
    log = tmp_path / "log.jsonl"

    monkeypatch.setenv("NEOS_ORIGIN_LOG", str(origin))
    monkeypatch.setenv("AVATAR_CEREMONY_LOG", str(ceremony))
    monkeypatch.setenv("NEOS_TEACH_CONTENT_LOG", str(teach))
    monkeypatch.setenv("NEOS_PERMISSION_COUNCIL_LOG", str(council))
    monkeypatch.setenv("NEOS_LOREBOOK_LOG", str(log))

    importlib.reload(nlw)

    # compile lorebook
    monkeypatch.setattr(sys, "argv", ["nlw", "compile", str(out)])
    nlw.main()
    capsys.readouterr()  # clear path output
    assert out.exists()
    data = json.loads(out.read_text())
    assert len(data) == 4
    assert log.exists()

    # gallery output
    monkeypatch.setattr(sys, "argv", ["nlw", "gallery"])
    nlw.main()
    gallery = json.loads(capsys.readouterr().out)
    assert len(gallery) == 4
