"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import json
import verify_audits as va
import audit_immutability as ai
from pathlib import Path


def test_directory_verification(tmp_path: Path) -> None:
    d = tmp_path / "logs"
    d.mkdir()
    log1 = d / "a.jsonl"
    log2 = d / "b.jsonl"
    ai.append_entry(log1, {"x": 1})
    last = ai.read_entries(log1)[-1].rolling_hash
    # create an entry in log2 that links back to log1
    ts = "2025-01-01T00:00:00"
    digest = ai._hash_entry(ts, {"y": 2}, last)
    entry = {"timestamp": ts, "data": {"y": 2}, "prev_hash": last, "rolling_hash": digest}
    log2.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    results, percent, stats = va.verify_audits(directory=d)
    assert all(not e for e in results.values())
    assert percent == 100.0
    assert stats == {"fixed": 0, "quarantined": 0, "unrecoverable": 0}
