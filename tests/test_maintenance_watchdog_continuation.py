import pytest
pytestmark=pytest.mark.no_legacy_skip
from sentientos import maintenance_loop_watchdog as w
from tests.test_maintenance_watchdog_scan import config

def test_tick_performs_exactly_one_top_level_transition(tmp_path):
    cfg=config(tmp_path); (tmp_path/'state'/'validation_ready.json').write_text('[{}]')
    out=w.tick(cfg,evaluation_time='t')
    assert out['transition']=='idle'
    ticks=(tmp_path/'state'/'watchdog_ticks.jsonl').read_text().splitlines()
    assert len(ticks)==1
