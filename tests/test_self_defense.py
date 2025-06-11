"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import importlib
import os
from pathlib import Path

import self_defense as sd


def setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SELF_DEFENSE_LOG", str(tmp_path / "log.jsonl"))
    importlib.reload(sd)


def test_quarantine_and_nullify(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    st = sd.self_quarantine("agent1", "suspect")
    assert st.quarantined
    st = sd.nullify_privilege("agent1", "sentinel")
    assert st.privilege_frozen
    log_file = Path(os.environ["SELF_DEFENSE_LOG"])
    assert log_file.exists()
    assert len(log_file.read_text().splitlines()) >= 2
