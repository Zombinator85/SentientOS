from __future__ import annotations
from pathlib import Path
import pytest
from sentientos import maintenance_wake_cycle as wake
from tests.test_maintenance_wake_cycle import _configured

pytestmark = pytest.mark.no_legacy_skip

def test_stop_appearing_after_probe_prevents_autonomy(monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    cfg=_configured(monkeypatch,tmp_path)
    def probe(_): (tmp_path/"STOP").touch(); return {"status":"health_probe_findings"}
    monkeypatch.setattr(wake.health,"probe_once",probe); monkeypatch.setattr(wake.autonomy,"cycle_once",lambda *a,**k:pytest.fail("autonomy ran"))
    result=wake.wake_once(cfg); assert result["status"]=="maintenance_wake_paused"; assert result["effect_counts"]["autonomy_cycle_invocations"]==0

def test_crash_after_probe_resumes_from_governed_custody_without_reprobe(monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    cfg=_configured(monkeypatch,tmp_path,sources=1); monkeypatch.setattr(wake.health,"probe_once",lambda c:pytest.fail("duplicate diagnostic")); monkeypatch.setattr(wake.autonomy,"cycle_once",lambda *a,**k:{"status":"autonomy_cycle_completed","receipt":None})
    assert wake.wake_once(cfg)["receipt"]["probe_skip_reason"]=="existing_governed_source"

def test_concurrent_owner_failure_has_zero_effects(monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    cfg=_configured(monkeypatch,tmp_path); monkeypatch.setattr(wake,"_lock",lambda c:(_ for _ in ()).throw(ValueError("wake_lock_unavailable")))
    result=wake.wake_once(cfg); assert result["status"]=="maintenance_wake_blocked"; assert sum(result["effect_counts"].values())==0

def test_completed_downstream_custody_is_continued_not_reprobed(monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    cfg=_configured(monkeypatch,tmp_path,action="continue_existing_work"); monkeypatch.setattr(wake.health,"probe_once",lambda c:pytest.fail("duplicate probe")); monkeypatch.setattr(wake.autonomy,"cycle_once",lambda *a,**k:{"status":"autonomy_cycle_idle","receipt":None})
    assert wake.wake_once(cfg)["effect_counts"]["autonomy_cycle_invocations"]==1
