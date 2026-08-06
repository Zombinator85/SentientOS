import pytest
pytestmark=pytest.mark.no_legacy_skip
from sentientos import maintenance_loop_watchdog as w
from tests.test_maintenance_watchdog_scan import config

def test_pause_resume_journal_and_stop_marker_fail_closed(tmp_path):
    cfg=config(tmp_path); w.control(cfg,'pause',evaluation_time='t1'); assert w.inspect_control(cfg)['paused']; w.control(cfg,'resume',evaluation_time='t2'); assert not w.inspect_control(cfg)['paused']
    (tmp_path/'state'/'STOP').touch(); assert w.tick(cfg,evaluation_time='t3')['status']=='paused'
