"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import hashlib
import os
import sys
from importlib import reload
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import privilege_lint as pl


BASELINE = Path("logs/privileged_audit.jsonl")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def test_audit_use_writes_runtime_and_keeps_baseline(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "audit"
    baseline_before = _sha(BASELINE)
    monkeypatch.setenv("SENTIENTOS_AUDIT_RUNTIME_DIR", str(runtime_dir))
    monkeypatch.delenv("SENTIENTOS_AUDIT_ALLOW_BASELINE_WRITE", raising=False)
    reload(pl)

    pl.audit_use("cli", "tool")

    runtime_path = runtime_dir / "privileged_audit.runtime.jsonl"
    assert runtime_path.exists()
    assert "tool" in runtime_path.read_text(encoding="utf-8")
    assert _sha(BASELINE) == baseline_before
