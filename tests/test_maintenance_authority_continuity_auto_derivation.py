import json
from pathlib import Path

import pytest

from sentientos import maintenance_authority_continuity_auto_derivation as auto
import sentientosd
from sentientos import maintenance_authority_continuity as continuity
from sentientos import maintenance_successor_generation_adoption as adoption
from sentientos import maintenance_wake_daemon_adoption as wake_daemon
from tests.test_maintenance_authority_continuity import canonical_custody
from tests.test_maintenance_successor_generation_adoption import canonical_lineage

pytestmark = pytest.mark.no_legacy_skip

NOW = "2030-01-02T00:00:00Z"


def _enabled_fixture(tmp_path: Path) -> tuple[dict[str, object], dict[str, object], Path, Path]:
    adoption_cfg, generation0, root = canonical_lineage(tmp_path, derive_successor=False)
    adoption_path = root / "successor-adoption.json"
    adoption_path.write_bytes(adoption.canonical_bytes(adoption_cfg) + b"\n")
    state = tmp_path / "auto-state"; evidence = tmp_path / "auto-evidence"
    state.mkdir(mode=0o700); evidence.mkdir(mode=0o700)
    cfg: dict[str, object] = {
        "schema_version": auto.CONFIG_SCHEMA, "enabled": True,
        "continuity_policy_path": adoption_cfg["continuity_policy_path"],
        "continuity_policy_digest": adoption_cfg["continuity_policy_digest"],
        "successor_adoption_config_path": str(adoption_path),
        "successor_adoption_config_digest": adoption_cfg["config_digest"],
        "repository_identity": adoption_cfg["repository_identity"],
        "repository_root": adoption_cfg["repository_root"], "state_root": str(state),
        "evidence_root": str(evidence), "journal_path": str(state / "events.jsonl"),
        "stop_marker": str(state / "STOP"), "observation_interval_seconds": 1,
        "maximum_successful_derivations": 2, "maximum_wall_clock_seconds": 60,
        "shutdown_timeout_seconds": 1, "config_digest": "",
    }
    cfg["config_digest"] = auto.digest(cfg, "config_digest")
    return auto.validate_config(cfg), generation0, root, evidence


def test_automatic_n0_to_n1_to_n2_recursion_without_manual_derive_next(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg, generation, root, evidence = _enabled_fixture(tmp_path)
    repository = Path(str(cfg["repository_root"]))
    calls = 0
    real_derive_next = continuity.derive_next
    def witnessed_derive_next(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return real_derive_next(*args, **kwargs)
    monkeypatch.setattr(auto.continuity, "derive_next", witnessed_derive_next)

    wake_events: list[tuple[str, int]] = []
    class Owner:
        def __init__(self, bound: dict[str, object]) -> None:
            path = str(bound["wake_config_path"])
            self.ordinal = int(Path(path).parent.name.split("-")[-1]) if "generation-" in path else 0
        def start(self) -> bool: wake_events.append(("start", self.ordinal)); return True
        def stop(self) -> bool: wake_events.append(("stop", self.ordinal)); return True
    successor_owner = adoption.MaintenanceSuccessorGenerationOwner(
        json.loads(Path(str(cfg["successor_adoption_config_path"])).read_text()), wake_owner_factory=Owner)
    initial_wake = wake_daemon.load_adoption(successor_owner.config["initial_wake_adoption_path"])
    successor_owner._owner = Owner(initial_wake)

    for ordinal in (0, 1):
        canonical_custody(tmp_path, repository, generation, ordinal, create_adapters=False,
                          state_root=tmp_path / "state")
        out = evidence / f"generation-{ordinal:06d}" / f"task{ordinal}"
        assert not (root / f"generation-{ordinal + 1}.json").exists()
        assert not (root / "receipts" / f"receipt-{ordinal + 1}.json").exists()
        assert not (out / "completion-v2.json").exists()
        assert not (out / "successor-v2.json").exists()
        result = auto.derive_once(cfg, evaluation_time=NOW)
        assert result["status"] == "successor_generation_derived"
        assert (out / "completion-v2.json").is_file() and (out / "successor-v2.json").is_file()
        assert successor_owner.handoff_once()["successor_ordinal"] == ordinal + 1
        generation, generated_wake = adoption.reconstruct_current(successor_owner.config)
        assert generation["ordinal"] == ordinal + 1
        assert wake_daemon.validate_adoption(generated_wake)["wake_config_digest"] == generated_wake["wake_config_digest"]

    assert calls == 2
    assert generation["ordinal"] == 2
    assert adoption.reconstruct_current(successor_owner.config)[0]["ordinal"] == 2
    assert wake_events == [("stop", 0), ("start", 1), ("stop", 1), ("start", 2)]
    assert [json.loads(line)["event_type"] for line in Path(str(cfg["journal_path"])).read_text().splitlines()] == list(auto.PHASES) * 2
    assert [json.loads(line)["event_type"] for line in Path(str(successor_owner.config["handoff_journal_path"])).read_text().splitlines()] == list(adoption.PHASES) * 2


def _prepared_transition(tmp_path: Path) -> tuple[dict[str, object], Path]:
    cfg, generation, root, _ = _enabled_fixture(tmp_path)
    canonical_custody(tmp_path, Path(str(cfg["repository_root"])), generation, 0,
                      create_adapters=False, state_root=tmp_path / "state")
    return cfg, root


def test_auto_controller_recovers_receipt_only_partial_continuity_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg, root = _prepared_transition(tmp_path)
    real_write = continuity._write
    interrupted = False
    def interrupt_generation(path: Path, value: dict[str, object]) -> str:
        nonlocal interrupted
        if path.name == "generation-1.json" and not interrupted:
            interrupted = True
            raise OSError("simulated_generation_persistence_interrupt")
        return real_write(path, value)
    monkeypatch.setattr(continuity, "_write", interrupt_generation)
    with pytest.raises(ValueError, match="continuity_derivation_failed"):
        auto.derive_once(cfg, evaluation_time=NOW)
    assert (root / "receipts/receipt-1.json").is_file() and not (root / "generation-1.json").exists()
    result = auto.derive_once(cfg, evaluation_time="2030-01-03T00:00:00Z")
    assert result["status"] == "successor_generation_derived"
    assert json.loads((root / "generation-1.json").read_text())["created_at"] == NOW


def test_auto_controller_recovers_generation_only_partial_continuity_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg, root = _prepared_transition(tmp_path)
    real_write = continuity._write
    skipped_receipt = False
    interrupted = False
    def interrupt_after_generation(path: Path, value: dict[str, object]) -> str:
        nonlocal skipped_receipt, interrupted
        if path.name == "receipt-1.json" and not skipped_receipt:
            skipped_receipt = True
            return "created"
        result = real_write(path, value)
        if path.name == "generation-1.json" and not interrupted:
            interrupted = True
            raise OSError("simulated_receipt_persistence_interrupt")
        return result
    monkeypatch.setattr(continuity, "_write", interrupt_after_generation)
    with pytest.raises(ValueError, match="continuity_derivation_failed"):
        auto.derive_once(cfg, evaluation_time=NOW)
    assert (root / "generation-1.json").is_file() and not (root / "receipts/receipt-1.json").exists()
    assert auto.derive_once(cfg, evaluation_time="2030-01-03T00:00:00Z")["status"] == "successor_generation_derived"
    assert json.loads((root / "receipts/receipt-1.json").read_text())["created_at"] == NOW


def test_auto_controller_recovers_complete_successor_with_missing_auto_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg, root = _prepared_transition(tmp_path)
    real_write = auto._write
    interrupted = False
    def interrupt_auto_receipt(path: Path, value: dict[str, object]) -> str:
        nonlocal interrupted
        if path.parent.name == "receipts" and not interrupted:
            interrupted = True
            raise OSError("simulated_auto_receipt_interrupt")
        return real_write(path, value)
    monkeypatch.setattr(auto, "_write", interrupt_auto_receipt)
    with pytest.raises(OSError, match="simulated_auto_receipt_interrupt"):
        auto.derive_once(cfg, evaluation_time=NOW)
    assert (root / "generation-1.json").is_file()
    assert len(auto._events(cfg)) == 3
    assert auto.derive_once(cfg, evaluation_time="2030-01-03T00:00:00Z")["status"] == "successor_generation_derived"
    assert len(auto._events(cfg)) == 4


def test_auto_controller_reuses_auto_receipt_when_only_final_event_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg, _ = _prepared_transition(tmp_path)
    real_append = auto._append
    interrupted = False
    def interrupt_final_event(config: dict[str, object], event_type: str, identity: dict[str, object], **extra: object) -> dict[str, object]:
        nonlocal interrupted
        if event_type == auto.PHASES[3] and not interrupted:
            interrupted = True
            raise OSError("simulated_final_event_interrupt")
        return real_append(config, event_type, identity, **extra)
    monkeypatch.setattr(auto, "_append", interrupt_final_event)
    with pytest.raises(OSError, match="simulated_final_event_interrupt"):
        auto.derive_once(cfg, evaluation_time=NOW)
    receipt_path = Path(str(cfg["state_root"])) / "receipts/receipt-1.json"
    before = receipt_path.read_bytes()
    assert auto.derive_once(cfg, evaluation_time="2030-01-03T00:00:00Z")["status"] == "successor_generation_derived"
    assert receipt_path.read_bytes() == before and len(auto._events(cfg)) == 4

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
