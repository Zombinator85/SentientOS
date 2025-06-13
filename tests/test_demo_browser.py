"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import time
from pathlib import Path
import demo_recorder as dr_mod


def test_scan_demos_sorted(tmp_path, monkeypatch):
    monkeypatch.setattr(dr_mod, "DEMO_DIR", tmp_path)
    f1 = tmp_path / "a.mp4"
    f1.write_bytes(b"0")
    time.sleep(0.01)
    f2 = tmp_path / "b.mp4"
    f2.write_bytes(b"0")
    demos = dr_mod._scan_demos()
    names = [d.path.name for d in demos]
    assert names == ["b.mp4", "a.mp4"]
