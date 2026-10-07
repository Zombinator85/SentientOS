"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from __future__ import annotations


from privilege_lint.env import report


def test_env_report_smoke():
    out = report()
    assert "Capability" in out
    assert "pyesprima" in out
    assert "MISSING" in out or "available" in out
