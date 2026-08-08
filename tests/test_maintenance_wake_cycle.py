from __future__ import annotations
import json
from pathlib import Path
import pytest
from sentientos import maintenance_wake_cycle as wake

pytestmark = pytest.mark.no_legacy_skip

class _Lock:
    def __enter__(self): return self
    def __exit__(self,*args): return None

def _configured(monkeypatch: pytest.MonkeyPatch,tmp_path: Path,*,action: str="collect",sources: int=0) -> dict[str,object]:
    cfg={"config_digest":"sha256:cfg","evaluation_time":"2030-01-01T00:00:00Z","stop_marker":str(tmp_path/"STOP"),"wake_receipt_journal_path":str(tmp_path/"receipts.jsonl")}
    monkeypatch.setattr(wake,"validate_config",lambda value:dict(value)); monkeypatch.setattr(wake,"_components",lambda value:({},{},{})); monkeypatch.setattr(wake,"_lock",lambda value:_Lock())
    monkeypatch.setattr(wake.autonomy,"inspect",lambda *a,**k:{"status":"inspection_ready","next_action":action})
    monkeypatch.setattr(wake.collector,"scan",lambda *a,**k:{"status":"scan_ready","source_count":sources})
    return cfg

def test_active_task_skips_probe_and_invokes_autonomy_once(monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    cfg=_configured(monkeypatch,tmp_path,action="continue_existing_work"); calls={"probe":0,"cycle":0}
    monkeypatch.setattr(wake.health,"probe_once",lambda c,**k:calls.__setitem__("probe",calls["probe"]+1))
    monkeypatch.setattr(wake.autonomy,"cycle_once",lambda *a,**k:(calls.__setitem__("cycle",calls["cycle"]+1) or {"status":"autonomy_cycle_continuing","receipt":None}))
    result=wake.wake_once(cfg); assert calls=={"probe":0,"cycle":1}; assert result["receipt"]["probe_skip_reason"]=="existing_autonomy_custody"

@pytest.mark.parametrize(("action","sources"),[("process_existing_candidate",0),("collect",1)])
def test_existing_candidate_or_governed_source_skips_probe(monkeypatch: pytest.MonkeyPatch,tmp_path: Path,action: str,sources: int) -> None:
    cfg=_configured(monkeypatch,tmp_path,action=action,sources=sources); monkeypatch.setattr(wake.health,"probe_once",lambda c,**k:pytest.fail("probe ran")); monkeypatch.setattr(wake.autonomy,"cycle_once",lambda *a,**k:{"status":"autonomy_cycle_idle","receipt":None})
    assert wake.wake_once(cfg)["effect_counts"]=={"health_probe_invocations":0,"autonomy_cycle_invocations":1}

def test_idle_healthy_has_zero_autonomy_effects(monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    cfg=_configured(monkeypatch,tmp_path); monkeypatch.setattr(wake.health,"probe_once",lambda c,**k:{"status":"health_probe_healthy"}); monkeypatch.setattr(wake.autonomy,"cycle_once",lambda *a,**k:pytest.fail("autonomy ran"))
    result=wake.wake_once(cfg); assert result["status"]=="maintenance_wake_idle"; assert result["effect_counts"]["autonomy_cycle_invocations"]==0

def test_idle_findings_invokes_autonomy_once(monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    cfg=_configured(monkeypatch,tmp_path); monkeypatch.setattr(wake.health,"probe_once",lambda c,**k:{"status":"health_probe_findings","governed_signal_path":"signal.json"}); monkeypatch.setattr(wake.autonomy,"cycle_once",lambda *a,**k:{"status":"autonomy_cycle_completed","receipt":{"terminal_custody":{"commit_sha":"abc"}}})
    result=wake.wake_once(cfg); assert result["effect_counts"]=={"health_probe_invocations":1,"autonomy_cycle_invocations":1}; assert result["receipt"]["terminal_custody"]=={"commit_sha":"abc"}

def test_stop_has_zero_effects(monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    cfg=_configured(monkeypatch,tmp_path); (tmp_path/"STOP").touch(); result=wake.wake_once(cfg); assert result["effect_counts"]=={"health_probe_invocations":0,"autonomy_cycle_invocations":0}

def test_receipt_tampering_blocks(monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    cfg=_configured(monkeypatch,tmp_path); (tmp_path/"receipts.jsonl").write_text(json.dumps({"receipt_digest":"bad"})+"\n"); assert wake.inspect_receipts(cfg)["status"]=="receipts_blocked"

def test_print_run_command_is_argv_only() -> None:
    result=wake.print_run_command("wake.json"); assert result["shell"] is False; assert result["scheduler_installation"] is False; assert result["argv"][-1]=="wake-once"

def test_explicit_evaluation_time_overrides_config_and_reaches_all_components(monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    cfg=_configured(monkeypatch,tmp_path); seen: list[tuple[str,str]]=[]
    monkeypatch.setattr(wake.autonomy,"inspect",lambda *a,**k:(seen.append(("inspect",k["evaluation_time"])) or {"status":"inspection_ready","next_action":"collect"}))
    monkeypatch.setattr(wake.collector,"scan",lambda *a,**k:(seen.append(("collector",k["evaluation_time"])) or {"status":"scan_ready","source_count":0}))
    monkeypatch.setattr(wake.health,"probe_once",lambda *a,**k:(seen.append(("health",k["evaluation_time"])) or {"status":"health_probe_findings","evaluation_time":k["evaluation_time"]}))
    monkeypatch.setattr(wake.autonomy,"cycle_once",lambda *a,**k:(seen.append(("autonomy",k["evaluation_time"])) or {"status":"autonomy_cycle_completed","receipt":None}))
    result=wake.wake_once(cfg,evaluation_time="2031-02-03T04:05:06Z")
    expected="2031-02-03T04:05:06.0000000Z"
    assert seen == [(name,expected) for name in ("inspect","collector","health","autonomy")]
    assert result["receipt"]["evaluation_time"] == expected
    assert result["receipt"]["health_probe_result"]["evaluation_time"] == expected
    assert cfg["evaluation_time"] == "2030-01-01T00:00:00Z"

def test_malformed_explicit_evaluation_time_blocks_before_effects(monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    cfg=_configured(monkeypatch,tmp_path)
    with pytest.raises(ValueError,match="invalid_evaluation_time"):
        wake.wake_once(cfg,evaluation_time="not-a-time")
