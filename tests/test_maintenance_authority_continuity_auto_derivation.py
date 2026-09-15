from pathlib import Path

import pytest

from sentientos import maintenance_authority_continuity_auto_derivation as auto

pytestmark = pytest.mark.no_legacy_skip

def disabled_config(tmp_path: Path) -> dict[str, object]:
    value: dict[str, object]={"schema_version":auto.CONFIG_SCHEMA,"enabled":False,"continuity_policy_path":"unused","continuity_policy_digest":"unused","successor_adoption_config_path":"unused","successor_adoption_config_digest":"unused","repository_identity":"repo","repository_root":str(tmp_path),"state_root":str(tmp_path/"state"),"evidence_root":str(tmp_path/"evidence"),"journal_path":str(tmp_path/"state"/"events.jsonl"),"stop_marker":str(tmp_path/"state"/"STOP"),"observation_interval_seconds":1,"maximum_successful_derivations":1,"maximum_wall_clock_seconds":10,"shutdown_timeout_seconds":1,"config_digest":""}
    value["config_digest"]=auto.digest(value,"config_digest")
    return value

def test_disabled_configuration_has_no_owner_or_effect(tmp_path: Path) -> None:
    cfg=auto.validate_config(disabled_config(tmp_path)); owner=auto.MaintenanceAuthorityContinuityAutoDerivationOwner(cfg)
    assert not owner.start()
    assert owner.health()=={"status":"disabled","read_only":True}
    assert auto.derive_once(cfg)["effect_count"]==0

def test_configuration_is_closed_and_digest_bound(tmp_path: Path) -> None:
    value=disabled_config(tmp_path); value["caller_selected_task_id"]="forbidden"
    with pytest.raises(ValueError,match="invalid_auto_derivation_config"): auto.validate_config(value)
    value=disabled_config(tmp_path); value["repository_identity"]="changed"
    with pytest.raises(ValueError,match="digest"): auto.validate_config(value)

def test_controller_has_no_handoff_or_resident_code_surface() -> None:
    source=Path(auto.__file__).read_text(encoding="utf-8")
    for forbidden in ("import subprocess", "import requests", "os.exec", "os.system", ".handoff_once(", "wake_owner_factory"):
        assert forbidden not in source
    assert '"wake_handoff_performed":False' in source
    assert '"resident_code_adoption_performed":False' in source
