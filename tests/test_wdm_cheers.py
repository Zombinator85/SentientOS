import yaml, os
from wdm.runner import run_wdm


def test_wdm_cheers_log(tmp_path) -> None:
    with open("config/wdm.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["activation"]["cheers_enabled"] = True
    cfg["logging"]["jsonl_path"] = str(tmp_path / "wdm") + "/"
    cfg["activation"]["cheers_channel"] = str(tmp_path / "wdm" / "cheers.jsonl")
    out = run_wdm("Hi from Cheers", {"cheers": True, "user_request": True}, cfg)
    assert out["rounds"] == 1
    assert os.path.exists(cfg["activation"]["cheers_channel"])

