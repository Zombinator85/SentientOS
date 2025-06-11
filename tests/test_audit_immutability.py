"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import json
from pathlib import Path
import audit_immutability as ai


def test_append_and_verify(tmp_path):
    log = tmp_path / "log.jsonl"
    entry1 = ai.append_entry(log, {"x": 1})
    entry2 = ai.append_entry(log, {"y": 2})
    assert entry1.data["emotion"] == "neutral"
    assert entry1.data["consent"] is True
    assert entry2.prev_hash == entry1.rolling_hash
    assert ai.verify(log)
    lines = log.read_text().splitlines()
    data = json.loads(lines[0])
    data["data"]["x"] = 42
    lines[0] = json.dumps(data)
    log.write_text("\n".join(lines))
    assert not ai.verify(log)
