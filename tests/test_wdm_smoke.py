"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from wdm.runner import run_wdm

def test_wdm_smoke():
    cfg = {
        "enabled": True, "max_rounds": 1,
        "initiation": {"triggers": ["user_request"]},
        "logging": {"jsonl_path": "logs_test/wdm/"},
        "allowlist": [{"id":"openai","adapter":"openai_live","enabled":True}]
    }
    ctx = {"user_request": True}
    out = run_wdm("Seed", ctx, cfg)
    assert out["decision"] in ("respond","initiate")
    assert out["log"].endswith(".jsonl")
