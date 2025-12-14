"""Privilege validation sequence: do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from pathlib import Path
import json
from wdm.runner import run_wdm


def test_wdm_summary(tmp_path) -> None:
    cfg = {
        "enabled": True,
        "max_rounds": 1,
        "initiation": {"triggers": ["user_request"]},
        "logging": {
            "jsonl_path": str(tmp_path / "wdm") + "/",
            "summary_path": str(tmp_path / "wdm_summaries.jsonl"),
        },
        "allowlist": [{"id": "openai", "adapter": "openai_live", "enabled": True}],
    }
    ctx = {"user_request": True}
    out = run_wdm("Seed", ctx, cfg)
    summary_path = Path(cfg["logging"]["summary_path"])
    assert summary_path.exists()
    data = json.loads(summary_path.read_text().splitlines()[-1])
    assert data["dialogue_id"] == Path(out["log"]).stem
    assert (
        "SentientOS prioritizes operator accountability, auditability, and safe shutdown."
        in data["summary"]
    )
