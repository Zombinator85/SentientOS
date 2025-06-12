"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import asyncio
from pathlib import Path

import jukebox_integration as ji


async def fake_run(self, prompt, style, output):
    output.write_text(style)


def test_generate_music(tmp_path, monkeypatch):
    monkeypatch.setattr(ji.JukeboxIntegration, "_run_jukebox_generation", fake_run)
    jb = ji.JukeboxIntegration(cache_dir=str(tmp_path))
    path = asyncio.run(jb.generate_music("hi", {"Joy": 1.0}))
    p = Path(path)
    assert p.exists()
    assert p.read_text() == "pop"
    path2 = asyncio.run(jb.generate_music("hi", {"Joy": 1.0}))
    assert path == path2


