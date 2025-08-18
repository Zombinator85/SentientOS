from pathlib import Path
import json
from wdm.runner import run_wdm


def test_presence_log(tmp_path):
    cfg = {
        "enabled": True,
        "max_rounds": 1,
        "initiation": {"triggers": ["user_request"]},
        "logging": {
            "jsonl_path": str(tmp_path / "wdm") + "/",
            "summary_path": str(tmp_path / "wdm_summaries.jsonl"),
            "presence_path": str(tmp_path / "presence.jsonl"),
        },
        "allowlist": [{"id": "openai", "adapter": "openai_live", "enabled": True}],
    }
    ctx = {"user_request": True}
    out = run_wdm("Seed", ctx, cfg)
    presence_path = Path(cfg["logging"]["presence_path"])
    assert presence_path.exists()
    data = json.loads(presence_path.read_text().splitlines()[-1])
    assert data["dialogue_id"] == Path(out["log"]).stem
    assert "agents" in data
    assert any("openai" in a for a in data["agents"])
