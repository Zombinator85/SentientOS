from pathlib import Path
import json
from wdm.runner import run_wdm


def test_presence_stream_log(tmp_path):
    cfg = {
        "enabled": True,
        "max_rounds": 1,
        "initiation": {"triggers": ["user_request"]},
        "logging": {
            "jsonl_path": str(tmp_path / "wdm") + "/",
            "summary_path": str(tmp_path / "wdm_summaries.jsonl"),
            "presence_path": str(tmp_path / "presence.jsonl"),
            "stream_path": str(tmp_path / "presence_stream.jsonl"),
        },
        "allowlist": [{"id": "openai", "adapter": "openai_live", "enabled": True}],
    }
    ctx = {"user_request": True}
    run_wdm("Seed", ctx, cfg)
    sp = Path(cfg["logging"]["stream_path"])
    assert sp.exists()
    lines = sp.read_text().splitlines()
    assert any(json.loads(l)["event"] == "start" for l in lines)
    assert any(json.loads(l)["event"] == "end" for l in lines)
