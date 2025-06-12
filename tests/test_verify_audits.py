"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import audit_immutability as ai
import verify_audits as va


def test_verify_valid_log(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    ai.append_entry(log, {"x": 1})
    ai.append_entry(log, {"y": 2})
    ok, errors, _ = va.check_file(log)
    assert ok
    assert errors == []


def test_verify_bad_line(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    log.write_text("{bad json}\n", encoding="utf-8")
    ok, errors, _ = va.check_file(log)
    assert not ok
    assert errors


def test_repair_mode(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    ai.append_entry(log, {"x": 1})
    ai.append_entry(log, {"y": 2})
    lines = log.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0] + ","  # introduce trailing comma
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    results, percent, stats = va.verify_audits(directory=tmp_path, repair=True, quarantine=True)
    assert percent == 100.0
    assert stats["fixed"] == 1
    assert stats["quarantined"] == 0
