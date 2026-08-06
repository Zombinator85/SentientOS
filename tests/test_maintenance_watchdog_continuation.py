import pytest
pytestmark=pytest.mark.no_legacy_skip
from sentientos import maintenance_loop_watchdog as w
from tests.test_maintenance_watchdog_scan import config

def test_tick_performs_exactly_one_top_level_transition(tmp_path):
    cfg=config(tmp_path); (tmp_path/'state'/'validation_ready.json').write_text('[{}]')
    calls=[]; out=w.tick(cfg,evaluation_time='t',handlers={'validate':lambda *_:(calls.append(1) or {'status':'completed'})})
    assert out['transition']=='validate' and calls==[1]
