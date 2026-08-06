import pytest
pytestmark=pytest.mark.no_legacy_skip
from sentientos import maintenance_loop_watchdog as w
from tests.test_maintenance_watchdog_scan import config

def test_recovery_precedes_new_effects(tmp_path):
    cfg=config(tmp_path); (tmp_path/'state'/'interrupted_operations.json').write_text('[{}]'); (tmp_path/'state'/'commit_ready.json').write_text('[{}]')
    assert w.tick(cfg,evaluation_time='t',handlers={'recover':lambda *_:{'status':'completed'}})['transition']=='recover'
