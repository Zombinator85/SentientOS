"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import importlib

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import reflex_manager as rm


def test_freeze_unfreeze(tmp_path):
    manager = rm.ReflexManager()
    rule = rm.ReflexRule(rm.OnDemandTrigger(), [], name="f")
    manager.add_rule(rule)
    manager.freeze_rule("f")
    manager.promote_rule("f")
    assert rule.status != "preferred"
    manager.unfreeze_rule("f")
    import final_approval
    importlib.reload(final_approval)
    rm.final_approval.request_approval = lambda *a, **k: True
    manager.promote_rule("f")
    assert rule.status == "preferred"


