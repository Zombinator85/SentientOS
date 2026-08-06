import pytest
pytestmark=pytest.mark.no_legacy_skip
from sentientos import maintenance_loop_watchdog as w
from tests.test_maintenance_watchdog_scan import config

def test_decision_uses_required_recovery_first_priority(tmp_path):
    cfg=config(tmp_path); s=w.scan(cfg,evaluation_time='t'); s['observations']['interrupted_operations']=[{}]; s['observations']['publication_queue']=[{}]; s['scan_digest']=w.digest({k:v for k,v in s.items() if k!='scan_digest'})
    assert w.decide(cfg,s)['transition']=='recover'
