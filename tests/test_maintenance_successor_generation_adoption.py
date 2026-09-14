from pathlib import Path
from datetime import datetime, timezone
import json

import pytest

from sentientos import maintenance_successor_generation_adoption as adoption
from sentientos import maintenance_activation_profiles as profiles
from sentientos import maintenance_authority_continuity as continuity
from sentientos import maintenance_loop_activation as activation
from sentientos import maintenance_loop_watchdog as watchdog
from sentientos import maintenance_candidate_collector as collector
from sentientos import maintenance_autonomy_cycle as autonomy
from sentientos import maintenance_health_probe as health
from sentientos import maintenance_wake_cycle as wake
from sentientos import maintenance_wake_daemon_adoption as wake_daemon
from tests.test_maintenance_authority_continuity import setup as continuity_setup, canonical_custody

pytestmark = pytest.mark.no_legacy_skip


def _write(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(adoption.canonical_bytes(value) + b"\n")
    return path


def canonical_lineage(tmp_path: Path) -> tuple[dict[str, object], dict[str, object], Path]:
    """Build genuine generation zero, its full wake closure, and derived N1."""
    policy_path, generation_path, generation, root, repository = continuity_setup(tmp_path)
    manifest = profiles.validate_manifest(json.loads(Path(generation["manifest_path"]).read_text()))
    for key in ("state_root", "workspace_root", "scratch_root", "inbox_root"):
        Path(manifest[key]).mkdir(mode=0o700)
    bundle = Path(manifest["output_directory"])
    watchdog_path = root / "watchdog-0.json"
    activation.render_config(watchdog_path, repository_root=repository, state_root=manifest["state_root"],
        workspace_root=manifest["workspace_root"], scratch_root=manifest["scratch_root"], inbox_root=manifest["inbox_root"],
        standing_grant=bundle / profiles.FILENAMES["standing_grant"], selector_policy=bundle / profiles.FILENAMES["selector_policy"],
        foreman_policy=bundle / profiles.FILENAMES["foreman_policy"], validation_policy=bundle / profiles.FILENAMES["validation_policy"],
        landing_policy=bundle / profiles.FILENAMES["landing_policy"], base_sha=generation["base_sha"],
        tracked_base_ref=manifest["tracked_base_ref"], implementation_backend="local_codex", commissioned_local_activation=None,
        maximum_actions=2, maximum_wall_clock_seconds=40, publication_retry_backoff_seconds=1)
    signals = tmp_path / "signals-0"; signals.mkdir(mode=0o700)
    collector_state = tmp_path / "collector-0"; collector_state.mkdir(mode=0o700)
    work_sources=tmp_path/"work-sources"; work_sources.mkdir(mode=0o700)
    cc = collector.validate_config({"schema_version":collector.CONFIG_SCHEMA,"repository_identity":"repo","repository_root":str(repository),"base_sha":generation["base_sha"],"activation_profile_bundle_manifest_path":generation["manifest_path"],"watchdog_configuration_path":str(watchdog_path),"collector_state_root":str(collector_state),"maintenance_candidate_inbox":manifest["inbox_root"],"governed_improvement_signal_source_roots":[str(signals)],"normalized_work_item_source_roots":[str(work_sources)],"allowed_source_schemas":[collector.GOVERNED_SIGNAL_SCHEMA],"allowed_source_kinds":["governed_improvement_signal"],"maximum_source_records_per_scan":2,"maximum_candidates_per_collection":1,"maximum_input_bytes_per_record":1000,"evaluation_time_required":True,"receipt_journal_path":str(collector_state/"receipts.jsonl"),"stop_marker":str(collector_state/"STOP")})
    collector_path = _write(root/"collector-0.json", cc)
    cycle_state=tmp_path/"cycle-0"; cycle_state.mkdir(mode=0o700)
    ac=autonomy.validate_config({"schema_version":autonomy.CONFIG_SCHEMA,"repository_identity":"repo","repository_root":str(repository),"base_sha":generation["base_sha"],"activation_profile_bundle_manifest_path":generation["manifest_path"],"collector_configuration_path":str(collector_path),"watchdog_configuration_path":str(watchdog_path),"external_cycle_state_root":str(cycle_state),"cycle_receipt_journal_path":str(cycle_state/"receipts.jsonl"),"stop_marker":str(cycle_state/"STOP"),"maximum_cycle_wall_clock_seconds":30,"maximum_collector_invocations_per_cycle":1,"maximum_watchdog_invocations_per_cycle":1,"maximum_candidates_collected_per_cycle":1,"remote_readiness_probe_required":False,"evaluation_time_required":True})
    autonomy_path=_write(root/"autonomy-0.json",ac)
    health_state=tmp_path/"health-0"; health_state.mkdir(mode=0o700)
    hc=health.validate_config({"schema_version":health.CONFIG_SCHEMA,"repository_identity":"repo","repository_root":str(repository),"base_sha":generation["base_sha"],"pytest_node_ids":["tests/fake.py::test_fake"],"probe_timeout_seconds":10,"maximum_failing_records":1,"probe_state_root":str(health_state),"governed_signal_output_root":str(signals),"declared_validation_expectations":["pytest_node:tests/fake.py::test_fake"],"requested_maintenance_authority_classes":["repository_commit"],"declared_constraints":["bounded"],"estimated_file_count":1,"estimated_changed_line_count":1,"estimated_implementation_seconds":1,"estimated_validation_seconds":1,"evaluation_time":"2030-01-02T00:00:00Z","receipt_journal_path":str(health_state/"receipts.jsonl")})
    health_path=_write(root/"health-0.json",hc)
    wake_state=tmp_path/"wake-0"; wake_state.mkdir(mode=0o700)
    wc=wake.validate_config({"schema_version":wake.CONFIG_SCHEMA,"repository_identity":"repo","repository_root":str(repository),"base_sha":generation["base_sha"],"health_probe_configuration_path":str(health_path),"autonomy_cycle_configuration_path":str(autonomy_path),"external_wake_state_root":str(wake_state),"wake_receipt_journal_path":str(wake_state/"receipts.jsonl"),"stop_marker":str(wake_state/"STOP"),"evaluation_time":"2030-01-02T00:00:00Z"})
    wake_path=_write(root/"wake-0.json",wc)
    cadence=tmp_path/"cadence-0"; cadence.mkdir(mode=0o700)
    adoption_path=root/"wake-adoption-0.json"
    activation.render_wake_daemon_adoption(adoption_path,wake_config_path=wake_path,cadence_state_root=cadence,enabled=True,cadence_interval_seconds=60,schedule_anchor_utc="2030-01-03T00:00:00Z",initial_run_posture="immediate",maximum_cycles=2,maximum_daemon_wall_clock_seconds=120,shutdown_timeout_seconds=1)
    initial=wake_daemon.load_adoption(adoption_path)
    cp,sp,_,_=canonical_custody(tmp_path,repository,generation,0)
    assert continuity.derive_next(policy_path,cp,sp,"2030-01-02T00:00:00Z")["status"] == "successor_generation_ready"
    (repository/".git/info/exclude").write_text("scripts/\ntests/\n")
    (repository/"scripts").mkdir(); (repository/"scripts/run_tests.py").write_text("")
    (repository/"tests").mkdir(); (repository/"tests/fake.py").write_text("def test_fake():\n    pass\n")
    successor=continuity.validate_generation(json.loads((root/"generation-1.json").read_text()),continuity.validate_policy(json.loads(policy_path.read_text())))
    cfg={"schema_version":adoption.CONFIG_SCHEMA,"enabled":True,"continuity_policy_path":str(policy_path),"continuity_policy_digest":json.loads(policy_path.read_text())["policy_digest"],"initial_generation_path":str(generation_path),"initial_generation_digest":generation["generation_digest"],"initial_wake_adoption_path":str(adoption_path),"initial_wake_adoption_digest":initial["adoption_config_digest"],"repository_identity":"repo","repository_root":str(repository),"state_root":str(tmp_path/"adoption-state"),"successor_configuration_root":str(tmp_path/"successor-output"),"handoff_journal_path":str(tmp_path/"adoption-state"/"handoffs.jsonl"),"stop_marker":str(tmp_path/"adoption-state"/"STOP"),"observation_delay_seconds":1,"maximum_handoffs":2,"maximum_wall_clock_seconds":60,"shutdown_timeout_seconds":1}
    for path in (Path(cfg["state_root"]),Path(cfg["successor_configuration_root"])): path.mkdir(mode=0o700)
    cfg["config_digest"]=adoption.digest(cfg)
    return cfg, successor, root


def test_canonical_builder_uses_manifest_roots_and_is_exactly_replayable(tmp_path: Path) -> None:
    cfg, successor, root = canonical_lineage(tmp_path)
    predecessor=continuity.validate_generation(json.loads((root/"generation-0.json").read_text()),continuity.validate_policy(json.loads(Path(cfg["continuity_policy_path"]).read_text())))
    current=wake_daemon.load_adoption(cfg["initial_wake_adoption_path"])
    first=adoption.build_successor_adoption(cfg,predecessor,current,successor)
    assert adoption.build_successor_adoption(cfg,predecessor,current,successor) == first
    generated=Path(cfg["successor_configuration_root"])/"generation-1"
    wd=watchdog.load_config(generated/"watchdog.json"); cc=collector.load_config(generated/"collector.json")
    ac=autonomy.load_config(generated/"autonomy.json"); hc=health.load_config(generated/"health.json"); wc=wake.load_config(generated/"wake.json")
    manifest=profiles.validate_manifest(json.loads(Path(successor["manifest_path"]).read_text()))
    assert wd["state_root"] == manifest["state_root"] and cc["maintenance_candidate_inbox"] == manifest["inbox_root"]
    assert manifest["inbox_root"] in wd["candidate_inbox_roots"] and hc["governed_signal_output_root"] in cc["governed_improvement_signal_source_roots"]
    wake._components(wc)
    autonomy._component_configs(ac, evaluation_time=wc["evaluation_time"])


def test_real_default_builder_hands_off_n0_to_n1_then_n1_to_n2(tmp_path: Path) -> None:
    cfg, successor, root = canonical_lineage(tmp_path)
    events: list[tuple[str, int]] = []
    class Owner:
        def __init__(self, bound: dict[str, object]) -> None:
            self.bound = bound
            self.ordinal = int(Path(str(bound["wake_config_path"])).parent.name.split("-")[-1]) if "generation-" in str(bound["wake_config_path"]) else 0
        def start(self) -> bool: events.append(("start", self.ordinal)); return True
        def stop(self) -> bool: events.append(("stop", self.ordinal)); return True
    owner=adoption.MaintenanceSuccessorGenerationOwner(cfg,wake_owner_factory=Owner)
    owner._owner=Owner(wake_daemon.load_adoption(cfg["initial_wake_adoption_path"]))
    assert owner.handoff_once()["successor_ordinal"] == 1
    assert events == [("stop",0),("start",1)]
    current,current_wake=adoption.reconstruct_current(cfg)
    assert current["ordinal"] == 1
    assert current_wake == wake_daemon.load_adoption(Path(cfg["successor_configuration_root"])/"generation-1/wake-adoption.json")
    policy=Path(cfg["continuity_policy_path"]); repository=Path(cfg["repository_root"])
    cp,sp,_,_=canonical_custody(tmp_path,repository,current,1)
    assert continuity.derive_next(policy,cp,sp,"2030-01-02T00:00:00Z")["status"] == "successor_generation_ready"
    assert owner.handoff_once()["successor_ordinal"] == 2
    assert events == [("stop",0),("start",1),("stop",1),("start",2)]
    assert adoption.reconstruct_current(cfg)[0]["ordinal"] == 2
    phases=[json.loads(line)["event_type"] for line in Path(cfg["handoff_journal_path"]).read_text().splitlines()]
    assert phases == list(adoption.PHASES) * 2


def disabled_config(tmp_path: Path) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": adoption.CONFIG_SCHEMA, "enabled": False,
        "continuity_policy_path": str(tmp_path / "policy.json"), "continuity_policy_digest": "sha256:p",
        "initial_generation_path": str(tmp_path / "generation.json"), "initial_generation_digest": "sha256:g",
        "initial_wake_adoption_path": str(tmp_path / "wake.json"), "initial_wake_adoption_digest": "sha256:w",
        "repository_identity": "Zombinator85/SentientOS", "repository_root": str(tmp_path),
        "state_root": str(tmp_path / "state"), "successor_configuration_root": str(tmp_path / "output"),
        "handoff_journal_path": str(tmp_path / "state" / "handoffs.jsonl"), "stop_marker": str(tmp_path / "state" / "STOP"),
        "observation_delay_seconds": 1, "maximum_handoffs": 2, "maximum_wall_clock_seconds": 60,
        "shutdown_timeout_seconds": 1,
    }
    value["config_digest"] = adoption.digest(value)
    return value


def test_disabled_configuration_starts_no_owner(tmp_path: Path) -> None:
    owner = adoption.MaintenanceSuccessorGenerationOwner(disabled_config(tmp_path))
    assert owner.start() is False
    assert owner.health() == {"status": "disabled", "read_only": True}


def test_configuration_is_closed_and_digest_bound(tmp_path: Path) -> None:
    value = disabled_config(tmp_path)
    assert adoption.validate_config(value)["config_digest"] == value["config_digest"]
    value["current_generation"] = 4
    with pytest.raises(ValueError, match="invalid_successor_adoption_config"):
        adoption.validate_config(value)


def test_controller_has_no_continuity_derivation_or_runtime_code_adoption() -> None:
    source = Path(adoption.__file__).read_text(encoding="utf-8")
    forbidden = ("derive_next(", "os.exec", "subprocess", "importlib", "git ", "requests")
    assert not any(item in source for item in forbidden)


def test_production_owner_installs_canonical_builder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = disabled_config(tmp_path); cfg["enabled"] = True
    monkeypatch.setattr(adoption, "validate_config", lambda value: dict(value))
    owner = adoption.MaintenanceSuccessorGenerationOwner(cfg)
    assert callable(owner._builder)


def test_background_owner_reports_deterministic_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = disabled_config(tmp_path); cfg.update(enabled=True, maximum_wall_clock_seconds=1)
    monkeypatch.setattr(adoption, "validate_config", lambda value: dict(value))
    owner = adoption.MaintenanceSuccessorGenerationOwner(cfg, waiter=lambda _: None,
        clock=lambda: datetime(2030, 1, 1, tzinfo=timezone.utc))
    monkeypatch.setattr(owner, "handoff_once", lambda: (_ for _ in ()).throw(ValueError("custody_ambiguous")))
    owner._run()
    assert owner.health() == {"status": "degraded", "read_only": True,
                              "reason": "custody_ambiguous", "terminal": True}
