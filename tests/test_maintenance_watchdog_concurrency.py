import pytest
pytestmark=pytest.mark.no_legacy_skip
import fcntl
from sentientos import maintenance_loop_watchdog as w
from tests.test_maintenance_watchdog_scan import config

def test_global_lock_prevents_duplicate_effect(tmp_path):
    cfg=config(tmp_path); p=tmp_path/'state'/'watchdog.lock'; p.touch()
    with p.open('r+') as h:
        fcntl.flock(h,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert w.tick(cfg,evaluation_time='t')['transition']=='global_lock_busy'
