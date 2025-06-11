"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import federation_trust_protocol as ftp


def setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("FEDERATION_NODES", str(tmp_path / "nodes.json"))
    monkeypatch.setenv("FEDERATION_TRUST_LOG", str(tmp_path / "log.jsonl"))
    importlib.reload(ftp)


def test_handshake_and_excommunicate(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    node = ftp.join("node1", "key1", "blessed")
    assert node.node_id == "node1"
    ftp.heartbeat("node1")
    ftp.revoke_trust("node1", "rogue")
    assert not ftp.list_nodes()["node1"].active
    ftp.leave("node1", ["c1", "c2"])
    data = ftp.list_nodes()["node1"]
    assert data.expelled
    log_file = Path(os.environ["FEDERATION_TRUST_LOG"])
    assert log_file.exists() and log_file.read_text().strip()

