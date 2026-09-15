from pathlib import Path

import pytest

from sentientos import maintenance_authority_continuity_auto_derivation as auto
import sentientosd

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

def test_sentientosd_starts_auto_only_after_successor_owner_reports_started(monkeypatch: pytest.MonkeyPatch) -> None:
    class Successor:
        def __init__(self, _config: object) -> None: pass
        def start(self) -> bool: return False
        def health(self) -> dict[str, object]: return {"status":"current_wake_owner_start_failed","read_only":True}
    class AutoOwner:
        starts = 0
        def __init__(self, config: dict[str, object]) -> None: self.config=config
        def start(self) -> bool: AutoOwner.starts += 1; return True
        def health(self) -> dict[str, object]: return {"status":"running","read_only":True}
    monkeypatch.setattr(sentientosd, "load_successor_adoption", lambda _p: {"enabled":True})
    monkeypatch.setattr(sentientosd, "MaintenanceSuccessorGenerationOwner", Successor)
    _, _, successor, overlap = sentientosd._start_maintenance_daemon_owners(None, None, "successor.json")
    assert successor is not None and overlap is False
    monkeypatch.setattr(sentientosd, "load_continuity_auto_derivation", lambda _p: {"successor_adoption_config_path":"successor.json"})
    monkeypatch.setattr(sentientosd, "MaintenanceAuthorityContinuityAutoDerivationOwner", AutoOwner)
    owner, health = sentientosd._start_maintenance_continuity_auto_derivation("auto.json", "successor.json", successor, overlap)
    assert owner is None and AutoOwner.starts == 0
    assert health["reason"] == "exact_successor_adoption_owner_not_running"

def test_sentientosd_starts_auto_after_exact_successor_owner_is_running(monkeypatch: pytest.MonkeyPatch) -> None:
    class Successor:
        def __init__(self, _config: object) -> None: pass
        def start(self) -> bool: return True
    class AutoOwner:
        def __init__(self, config: dict[str, object]) -> None: self.config=config
        def start(self) -> bool: return True
        def health(self) -> dict[str, object]: return {"status":"running","read_only":True}
    monkeypatch.setattr(sentientosd, "load_successor_adoption", lambda _p: {"enabled":True})
    monkeypatch.setattr(sentientosd, "MaintenanceSuccessorGenerationOwner", Successor)
    _, _, successor, overlap = sentientosd._start_maintenance_daemon_owners(None, None, "successor.json")
    monkeypatch.setattr(sentientosd, "load_continuity_auto_derivation", lambda _p: {"successor_adoption_config_path":"successor.json"})
    monkeypatch.setattr(sentientosd, "MaintenanceAuthorityContinuityAutoDerivationOwner", AutoOwner)
    owner, health = sentientosd._start_maintenance_continuity_auto_derivation("auto.json", "successor.json", successor, overlap)
    assert owner is not None and health["status"] == "running"

def test_journal_replay_rejects_changed_authority_binding(tmp_path: Path) -> None:
    cfg = auto.validate_config(disabled_config(tmp_path))
    identity = {"lineage_id":"line","adopted_ordinal":0,"adopted_generation_digest":"sha256:g",
                "task_id":"task","closure_event_digest":"sha256:c","evaluation_time":"2030-01-01T00:00:00Z"}
    auto._append(cfg, auto.PHASES[0], identity)
    auto._append(cfg, auto.PHASES[1], identity, completion_adapter_digest="sha256:a", successor_adapter_digest="sha256:b")
    auto._append(cfg, auto.PHASES[2], identity, completion_adapter_digest="sha256:changed", successor_adapter_digest="sha256:b")
    # _append permits only syntactically valid append operations; replay owns
    # cross-phase authority consistency and must reject the digest-valid fork.
    with pytest.raises(ValueError, match="journal_branched"):
        auto._events(cfg)
