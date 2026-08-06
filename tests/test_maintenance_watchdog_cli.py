import pytest
pytestmark=pytest.mark.no_legacy_skip
import json
from scripts.maintenance_loop_watchdog import main
from tests.test_maintenance_watchdog_scan import config

def test_cli_doctor_requires_explicit_valid_config(tmp_path,capsys):
    p=tmp_path/'config.json'; p.write_text(json.dumps(config(tmp_path)))
    assert main(['--config',str(p),'doctor'])==0
    assert json.loads(capsys.readouterr().out)['status']=='watchdog_config_ready'
