import pytest
pytestmark=pytest.mark.no_legacy_skip
from sentientos import maintenance_loop_watchdog as w
from tests.test_maintenance_watchdog_scan import config

def test_recovery_precedes_new_effects(tmp_path):
    cfg=config(tmp_path); (tmp_path/'state'/'interrupted_operations.json').write_text('[{}]'); (tmp_path/'state'/'commit_ready.json').write_text('[{}]')
    # Legacy summaries have no authority to drive effects.
    assert w.tick(cfg,evaluation_time='t')['transition']=='idle'

def test_public_handler_injection_is_not_accepted(tmp_path):
    with pytest.raises(TypeError):
        w.tick(config(tmp_path), evaluation_time='t', handlers={})
