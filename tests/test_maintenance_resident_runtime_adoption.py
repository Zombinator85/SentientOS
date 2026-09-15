import json
import fcntl
import os
import subprocess
import sys
from pathlib import Path

import pytest

import sentientosd
from sentientos import maintenance_authority_continuity as continuity
from sentientos import maintenance_resident_runtime_adoption as resident
from sentientos import maintenance_successor_generation_adoption as adoption
from sentientos import maintenance_wake_daemon_adoption as wake_daemon
from tests.test_maintenance_authority_continuity import canonical_custody
from tests.test_maintenance_successor_generation_adoption import canonical_lineage

pytestmark = pytest.mark.no_legacy_skip
NOW = "2030-01-02T00:00:00Z"


def _write(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(adoption.canonical_bytes(value) + b"\n")


def _fixture(tmp_path: Path) -> tuple[dict[str, object], dict[str, object], Path, Path]:
    successor_cfg, generation, custody = canonical_lineage(tmp_path, derive_successor=False)
    repository = Path(str(successor_cfg["repository_root"]))
    with (repository / ".git/info/exclude").open("a") as handle:
        handle.write("sentientosd.py\n")
    (repository / "sentientosd.py").write_text("# canonical daemon entrypoint\n")
    successor_path = custody / "successor-adoption.json"; _write(successor_path, successor_cfg)
    state = tmp_path / "resident-state"; state.mkdir(mode=0o700)
    config_path = tmp_path / "resident.json"
    cfg: dict[str, object] = {"schema_version": resident.CONFIG_SCHEMA, "enabled": True,
        "continuity_policy_path": successor_cfg["continuity_policy_path"],
        "continuity_policy_digest": successor_cfg["continuity_policy_digest"],
        "successor_adoption_config_path": str(successor_path), "successor_adoption_config_digest": successor_cfg["config_digest"],
        "automatic_continuity_config_path": "", "automatic_continuity_config_digest": "",
        "repository_identity": "repo", "repository_root": str(repository.resolve()),
        "python_executable": str(Path(sys.executable).resolve()), "daemon_module": "sentientosd",
        "daemon_entrypoint": str((repository / "sentientosd.py").resolve()), "working_directory": str(repository.resolve()),
        "inherited_environment_allowlist": ["PATH"], "required_environment": {
            resident.CONFIG_ENV: str(config_path.resolve()),
            resident.SUCCESSOR_CONFIG_ENV: str(successor_path.resolve()),
        },
        "state_root": str(state), "transition_journal_path": str(state / "transitions.jsonl"),
        "provenance_root": str(state / "provenance"), "receipt_root": str(state / "receipts"),
        "stop_marker": str(state / "STOP"), "quiescence_timeout_seconds": 2,
        "readiness_timeout_seconds": 20, "maximum_successful_transitions": 2,
        "maximum_wall_clock_seconds": 120, "config_digest": ""}
    cfg["config_digest"] = resident.digest(cfg, "config_digest"); _write(config_path, cfg)
    return cfg, generation, custody, repository


def _observer(cfg: dict[str, object], instance: int = 1) -> dict[str, object]:
    return {"python_executable": cfg["python_executable"], "daemon_entrypoint": cfg["daemon_entrypoint"],
            "cwd": cfg["working_directory"], "argv": [cfg["python_executable"], "-m", "sentientosd"],
            "pid": instance, "startup_timestamp": f"2030-01-02T00:00:0{instance}Z"}


class Owner:
    starts: list[int] = []
    def __init__(self, bound: dict[str, object]) -> None:
        path = str(bound["wake_config_path"])
        self.ordinal = int(Path(path).parent.name.split("-")[-1]) if "generation-" in path else 0
    def start(self) -> bool: self.starts.append(self.ordinal); return True
    def stop(self) -> bool: return True


def _advance(tmp_path: Path, cfg: dict[str, object], generation: dict[str, object], ordinal: int) -> dict[str, object]:
    repository = Path(str(cfg["repository_root"])); policy = Path(str(cfg["continuity_policy_path"]))
    cp, sp, _, _ = canonical_custody(tmp_path, repository, generation, ordinal)
    assert continuity.derive_next(policy, cp, sp, NOW)["status"] == "successor_generation_ready"
    root = Path(json.loads(policy.read_text())["generation_root"])
    return json.loads((root / f"generation-{ordinal + 1}.json").read_text())


def _pending_owner(cfg: dict[str, object], controller: resident.MaintenanceResidentRuntimeAdoptionController) -> adoption.MaintenanceSuccessorGenerationOwner:
    successor_cfg = adoption.load_config(str(cfg["successor_adoption_config_path"]))
    owner = adoption.MaintenanceSuccessorGenerationOwner(successor_cfg, wake_owner_factory=Owner,
        successor_start_readiness_guard=controller.readiness_guard)
    owner._owner = Owner(wake_daemon.load_adoption(successor_cfg["initial_wake_adoption_path"]))
    assert owner.handoff_once()["status"] == "waiting_for_resident_runtime_readiness"
    return owner


def test_exact_launch_and_repository_provenance_is_per_process(tmp_path: Path) -> None:
    cfg, generation, _, repository = _fixture(tmp_path)
    first = resident.MaintenanceResidentRuntimeAdoptionController(cfg, process_observer=lambda: _observer(cfg, 1)).capture_baseline()
    second = resident.MaintenanceResidentRuntimeAdoptionController(cfg, process_observer=lambda: _observer(cfg, 2)).capture_baseline()
    assert first["provenance_path"] != second["provenance_path"]
    assert Path(first["provenance_path"]).is_file() and first["observed_head_sha"] == generation["base_sha"]
    (repository / "dirty").write_text("x")
    with pytest.raises(ValueError, match="repository_state"):
        resident.MaintenanceResidentRuntimeAdoptionController(cfg, process_observer=lambda: _observer(cfg, 3)).capture_baseline()


def test_config_consumes_canonical_digest_bindings(tmp_path: Path) -> None:
    cfg, _, _, _ = _fixture(tmp_path)
    assert resident.validate_config(cfg)["successor_adoption_config_digest"] == cfg["successor_adoption_config_digest"]
    bad = dict(cfg); bad["continuity_policy_digest"] = "sha256:wrong"; bad["config_digest"] = resident.digest(bad, "config_digest")
    with pytest.raises(ValueError, match="continuity_policy_digest_mismatch"): resident.validate_config(bad)
    bad = dict(cfg); bad["daemon_entrypoint"] = str(Path(str(cfg["repository_root"])) / "other.py"); bad["config_digest"] = resident.digest(bad, "config_digest")
    with pytest.raises((ValueError, FileNotFoundError)): resident.validate_config(bad)


def test_exact_pre_exec_canonical_pending_handoff_eligibility(tmp_path: Path) -> None:
    cfg, generation, _, _ = _fixture(tmp_path); calls: list[tuple[str, list[str], object]] = []
    controller = resident.MaintenanceResidentRuntimeAdoptionController(cfg, process_observer=lambda: _observer(cfg),
        execve=lambda e, a, v: calls.append((e, a, v)))
    controller.capture_baseline()
    with pytest.raises(ValueError, match="handoff_not_eligible"): controller.request_replacement()
    _advance(tmp_path, cfg, generation, 0); owner = _pending_owner(cfg, controller)
    with pytest.raises(ValueError, match="caller_handoff_not_canonical"):
        controller.request_replacement({"fabricated": True})
    result = controller.request_replacement(quiesce=lambda timeout: timeout == 2)
    assert len(calls) == 1 and calls[0][1] == [cfg["python_executable"], "-m", "sentientosd"]
    assert not controller.readiness_guard(adoption.pending_handoff(owner.config))
    assert result["transition_id"] == calls[0][2][resident.TRANSITION_ENV]


def test_post_exec_marker_provenance_and_readiness_recovery(tmp_path: Path) -> None:
    cfg, generation, _, _ = _fixture(tmp_path)
    old = resident.MaintenanceResidentRuntimeAdoptionController(cfg, process_observer=lambda: _observer(cfg, 1), execve=lambda *_: None)
    old.capture_baseline(); _advance(tmp_path, cfg, generation, 0); owner = _pending_owner(cfg, old)
    transition = old.request_replacement(quiesce=lambda _: True)
    new = resident.MaintenanceResidentRuntimeAdoptionController(cfg, process_observer=lambda: _observer(cfg, 2))
    with pytest.raises(ValueError, match="marker_mismatch"): new.complete_post_exec(marker="sha256:wrong")
    receipt = new.complete_post_exec(marker=transition["transition_id"])
    handoff = adoption.pending_handoff(owner.config)
    assert receipt["successor_launch_provenance_digest"] and new.readiness_guard(handoff)
    assert not old.readiness_guard(handoff)
    owner._successor_start_readiness_guard = new.readiness_guard
    assert owner.handoff_once()["status"] == "handoff_completed"
    assert 1 in Owner.starts


def test_quiescence_stop_count_and_time_bounds_fail_closed(tmp_path: Path) -> None:
    cfg, generation, _, _ = _fixture(tmp_path)
    controller = resident.MaintenanceResidentRuntimeAdoptionController(cfg, process_observer=lambda: _observer(cfg), execve=lambda *_: None)
    controller.capture_baseline(); _advance(tmp_path, cfg, generation, 0); _pending_owner(cfg, controller)
    with pytest.raises(ValueError, match="quiescence_timeout"): controller.request_replacement(quiesce=lambda _: False)
    assert controller.health()["status"] == "blocked"
    # STOP denies a fresh transition before an exec request is journalled.
    other = tmp_path / "other"; other.mkdir()
    cfg2, generation2, _, _ = _fixture(other)
    controller2 = resident.MaintenanceResidentRuntimeAdoptionController(cfg2, process_observer=lambda: _observer(cfg2))
    controller2.capture_baseline(); _advance(other, cfg2, generation2, 0); _pending_owner(cfg2, controller2)
    Path(str(cfg2["stop_marker"])).touch()
    with pytest.raises(ValueError, match="paused"): controller2.request_replacement()


def test_sentientosd_drives_resident_transition_before_successor_wake(tmp_path: Path) -> None:
    Owner.starts.clear()
    cfg, generation, _, _ = _fixture(tmp_path); calls: list[object] = []
    controller = resident.MaintenanceResidentRuntimeAdoptionController(cfg, process_observer=lambda: _observer(cfg), execve=lambda *v: calls.append(v))
    controller.capture_baseline(); _advance(tmp_path, cfg, generation, 0); owner = _pending_owner(cfg, controller)
    result = sentientosd._drive_resident_runtime_transition(controller, owner, None)
    assert result and result["status"] == "self_exec_requested" and len(calls) == 1
    assert 1 not in Owner.starts


def test_sentientosd_post_exec_recovery_unlocks_successor_wake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    Owner.starts.clear()
    cfg, generation, _, _ = _fixture(tmp_path)
    old = resident.MaintenanceResidentRuntimeAdoptionController(cfg, process_observer=lambda: _observer(cfg, 1), execve=lambda *_: None)
    old.capture_baseline(); _advance(tmp_path, cfg, generation, 0); owner = _pending_owner(cfg, old)
    transition = old.request_replacement(quiesce=lambda _: True)
    monkeypatch.setenv(resident.TRANSITION_ENV, transition["transition_id"])
    new = resident.MaintenanceResidentRuntimeAdoptionController(cfg, process_observer=lambda: _observer(cfg, 2))
    sentientosd._prepare_resident_runtime_startup(new)
    owner._successor_start_readiness_guard = new.readiness_guard
    assert owner.handoff_once()["status"] == "handoff_completed" and 1 in Owner.starts


def test_resident_runtime_n0_to_n1_to_n2_behavioral_closure(tmp_path: Path) -> None:
    Owner.starts.clear(); cfg, generation, _, _ = _fixture(tmp_path)
    controller = resident.MaintenanceResidentRuntimeAdoptionController(cfg, process_observer=lambda: _observer(cfg, 1), execve=lambda *_: None)
    controller.capture_baseline()
    for ordinal in (0, 1):
        next_generation = _advance(tmp_path, cfg, generation, ordinal)
        owner = _pending_owner(cfg, controller)
        transition = controller.request_replacement(quiesce=lambda _: True)
        controller = resident.MaintenanceResidentRuntimeAdoptionController(cfg, process_observer=lambda n=ordinal: _observer(cfg, n + 2), execve=lambda *_: None)
        controller.complete_post_exec(marker=transition["transition_id"])
        owner._successor_start_readiness_guard = controller.readiness_guard
        assert owner.handoff_once()["status"] == "handoff_completed"
        generation = next_generation
    assert Owner.starts[-2:] == [1, 2]
    phases = [json.loads(line)["phase"] for line in Path(str(cfg["transition_journal_path"])).read_text().splitlines()]
    assert phases == list(resident.PHASES) * 2


def test_generic_service_and_process_authority_remains_absent() -> None:
    source = Path(resident.__file__).read_text()
    assert "Popen(" not in source and "system(" not in source and "service restart" not in source


def test_exec_environment_reconstructs_exact_new_image_topology(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg, generation, _, _ = _fixture(tmp_path); calls: list[tuple[str, list[str], dict[str, str]]] = []
    old = resident.MaintenanceResidentRuntimeAdoptionController(cfg, process_observer=lambda: _observer(cfg, 1),
        execve=lambda executable, argv, env: calls.append((executable, argv, dict(env))))
    old.capture_baseline(); _advance(tmp_path, cfg, generation, 0); owner = _pending_owner(cfg, old)
    transition = old.request_replacement(quiesce=lambda _: True); env = calls[0][2]
    for name in (resident.CONFIG_ENV, resident.SUCCESSOR_CONFIG_ENV, resident.AUTO_CONFIG_ENV, resident.TRANSITION_ENV):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items(): monkeypatch.setenv(name, value)
    recovered = resident.load_config(os.environ[resident.CONFIG_ENV])
    assert adoption.load_config(os.environ[resident.SUCCESSOR_CONFIG_ENV])["config_digest"] == cfg["successor_adoption_config_digest"]
    observation = _observer(cfg, 2); observation["environment"] = {
        "PYTHONPATH": None, "PYTHONHOME": None, resident.TRANSITION_ENV: transition["transition_id"],
        resident.CONFIG_ENV: os.environ[resident.CONFIG_ENV], resident.SUCCESSOR_CONFIG_ENV: os.environ[resident.SUCCESSOR_CONFIG_ENV],
        resident.AUTO_CONFIG_ENV: None,
    }
    new = resident.MaintenanceResidentRuntimeAdoptionController(recovered, process_observer=lambda: observation)
    sentientosd._prepare_resident_runtime_startup(new)
    owner._successor_start_readiness_guard = new.readiness_guard
    assert owner.handoff_once()["status"] == "handoff_completed"


def test_required_topology_environment_and_stable_process_identity(tmp_path: Path) -> None:
    cfg, _, _, _ = _fixture(tmp_path)
    for missing in (resident.CONFIG_ENV, resident.SUCCESSOR_CONFIG_ENV):
        bad = dict(cfg); bad["required_environment"] = dict(cfg["required_environment"]); bad["required_environment"].pop(missing)
        bad["config_digest"] = resident.digest(bad, "config_digest")
        with pytest.raises(ValueError, match="topology_environment"): resident.validate_config(bad)
    controller = resident.MaintenanceResidentRuntimeAdoptionController(cfg, process_observer=lambda: _observer(cfg, 9))
    assert controller.capture_baseline()["process_instance_id"] == controller.capture_baseline()["process_instance_id"]


def test_transition_lock_contention_and_journal_mtime_is_not_authority(tmp_path: Path) -> None:
    cfg, generation, _, _ = _fixture(tmp_path); calls: list[object] = []
    controller = resident.MaintenanceResidentRuntimeAdoptionController(cfg, process_observer=lambda: _observer(cfg, 1), execve=lambda *v: calls.append(v))
    controller.capture_baseline(); _advance(tmp_path, cfg, generation, 0); _pending_owner(cfg, controller)
    lock_path = Path(str(cfg["state_root"])) / "resident-transition.lock"; handle = lock_path.open("a+b")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    with pytest.raises(ValueError, match="lock_busy"): controller.request_replacement(quiesce=lambda _: True)
    assert not calls
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN); handle.close()
    transition = controller.request_replacement(quiesce=lambda _: True)
    journal = Path(str(cfg["transition_journal_path"])); os.utime(journal, (1, 1))
    new = resident.MaintenanceResidentRuntimeAdoptionController(cfg, clock=lambda: float(json.loads(journal.read_text().splitlines()[3])["request_timestamp"]) + 1,
        process_observer=lambda: _observer(cfg, 2))
    assert new.complete_post_exec(marker=transition["transition_id"])["status"] == "resident_ready"
    assert new.complete_post_exec(marker=transition["transition_id"])["status"] == "resident_ready"


def _interrupt_pre_exec_prefix(
    monkeypatch: pytest.MonkeyPatch,
    controller: resident.MaintenanceResidentRuntimeAdoptionController,
    phase_index: int,
) -> None:
    original = resident._append

    def interrupt_after_append(*args, **kwargs):  # type: ignore[no-untyped-def]
        row = original(*args, **kwargs)
        if row["phase"] == resident.PHASES[phase_index]:
            raise RuntimeError("simulated_pre_exec_interruption")
        return row

    with monkeypatch.context() as scoped:
        scoped.setattr(resident, "_append", interrupt_after_append)
        with pytest.raises(RuntimeError, match="simulated_pre_exec_interruption"):
            controller.request_replacement(quiesce=lambda _: True)


@pytest.mark.parametrize("phase_index", (0, 1, 2))
def test_same_process_pre_exec_prefix_continuation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase_index: int
) -> None:
    cfg, generation, _, _ = _fixture(tmp_path); calls: list[object] = []
    controller = resident.MaintenanceResidentRuntimeAdoptionController(
        cfg, process_observer=lambda: _observer(cfg, 1), execve=lambda *args: calls.append(args))
    controller.capture_baseline(); _advance(tmp_path, cfg, generation, 0); _pending_owner(cfg, controller)
    _interrupt_pre_exec_prefix(monkeypatch, controller, phase_index)
    before = len(Path(str(cfg["transition_journal_path"])).read_text().splitlines())
    result = controller.request_replacement(quiesce=lambda _: True)
    assert before == phase_index + 1
    assert result["status"] == "self_exec_requested" and len(calls) == 1


@pytest.mark.parametrize("phase_index", (0, 1, 2))
def test_foreign_process_pre_exec_prefix_continuation_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase_index: int
) -> None:
    Owner.starts.clear(); cfg, generation, _, _ = _fixture(tmp_path); exec_calls: list[object] = []
    predecessor = resident.MaintenanceResidentRuntimeAdoptionController(
        cfg, process_observer=lambda: _observer(cfg, 1), execve=lambda *args: exec_calls.append(args))
    predecessor.capture_baseline(); _advance(tmp_path, cfg, generation, 0); _pending_owner(cfg, predecessor)
    _interrupt_pre_exec_prefix(monkeypatch, predecessor, phase_index)
    journal = Path(str(cfg["transition_journal_path"])); before = journal.read_bytes()
    foreign = resident.MaintenanceResidentRuntimeAdoptionController(
        cfg, process_observer=lambda: _observer(cfg, 2), execve=lambda *args: exec_calls.append(args))
    with pytest.raises(ValueError, match="foreign_predecessor_process_provenance"):
        foreign.capture_baseline()
    assert journal.read_bytes() == before
    assert exec_calls == [] and 1 not in Owner.starts


@pytest.mark.parametrize("phase_index", (0, 1, 2, 3))
def test_no_marker_fresh_restart_with_incomplete_transition_is_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase_index: int
) -> None:
    cfg, generation, _, _ = _fixture(tmp_path)
    predecessor = resident.MaintenanceResidentRuntimeAdoptionController(
        cfg, process_observer=lambda: _observer(cfg, 1), execve=lambda *_: None)
    predecessor.capture_baseline(); _advance(tmp_path, cfg, generation, 0); _pending_owner(cfg, predecessor)
    _interrupt_pre_exec_prefix(monkeypatch, predecessor, phase_index)
    monkeypatch.delenv(resident.TRANSITION_ENV, raising=False)
    restarted = resident.MaintenanceResidentRuntimeAdoptionController(
        cfg, process_observer=lambda: _observer(cfg, 2), execve=lambda *_: None)
    with pytest.raises(ValueError, match="foreign_predecessor_process_provenance"):
        sentientosd._prepare_resident_runtime_startup(restarted)
