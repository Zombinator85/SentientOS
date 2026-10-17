import json
import os
from pathlib import Path
from typing import Any

import pytest

from sentientos import maintenance_resident_runtime_adoption as resident
from sentientos.maintenance_resident_parent_supervision import (
    MaintenanceResidentParentSupervisor, ResidentParentLifecycleEvidenceReader,
)
from sentientos.runtime.services import HealthResult
from tests.test_maintenance_resident_runtime_adoption import _fixture, _journal_prefix

pytestmark = pytest.mark.no_legacy_skip


class FakeChild:
    def __init__(self, *, name: str, argv: tuple[str, ...], cwd: Path,
                 environment: dict[str, str], wrong: str = "") -> None:
        self.name, self.argv, self.cwd, self.environment = name, argv, cwd, environment
        self.pid = 40; self.alive = False; self.starts = 0; self.wrong = wrong

    @property
    def identity(self) -> dict[str, Any]:
        value = {"adapter": "child_process", "name": self.name, "argv": self.argv,
                 "cwd": str(self.cwd), "pid": self.pid if self.alive else None}
        if self.wrong == "argv": value["argv"] = (self.argv[0], "other.py")
        if self.wrong == "cwd": value["cwd"] = str(self.cwd.parent)
        return value

    def start(self) -> None:
        self.starts += 1; self.pid += 1; self.alive = True

    def health(self) -> HealthResult:
        return HealthResult(self.alive, "process_alive" if self.alive else "process_exited")

    def stop(self) -> None: self.alive = False
    def force_stop(self) -> None: self.alive = False


class Factory:
    def __init__(self, wrong: str = "") -> None: self.children: list[FakeChild] = []; self.wrong = wrong
    def __call__(self, **kwargs: Any) -> FakeChild:
        child = FakeChild(**kwargs, wrong=self.wrong); self.children.append(child); return child


def _parent(
    tmp_path: Path, *, ready: list[bool] | None = None, budget: int = 2,
    factory: Factory | None = None, process_presence_observer: Any = None,
    process_start_ticks_observer: Any = None,
) -> tuple[MaintenanceResidentParentSupervisor, FakeChild, dict[str, object]]:
    cfg, _, _, _ = _fixture(tmp_path)
    readiness = ready if ready is not None else [False]
    made = factory or Factory()
    controller = MaintenanceResidentParentSupervisor(cfg, state_root=tmp_path / "parent",
        resident_readiness_guard=lambda _: readiness[0], restart_budget=budget,
        min_backoff=0, max_backoff=0, adapter_factory=made,
        process_presence_observer=process_presence_observer,
        process_start_ticks_observer=process_start_ticks_observer)
    return controller, made.children[-1], cfg



def _simulate_parent_process_exit(controller: MaintenanceResidentParentSupervisor) -> None:
    """Close held custody descriptors to model kernel release at process exit."""
    descriptor = controller._owner_lock_fd
    if descriptor is not None:
        os.close(descriptor)
        controller._owner_lock_fd = None
    root_fd = controller._owner_root_fd
    if root_fd is not None:
        os.close(root_fd)
        controller._owner_root_fd = None


def test_commissioned_parent_config_is_explicitly_handed_to_child(tmp_path: Path) -> None:
    from sentientos import maintenance_resident_parent_supervision as parent

    cfg, _generation, _custody, _repository = _fixture(tmp_path)
    config_path = Path(str(cfg[resident.CONFIG_ENV])).resolve(strict=True)
    child_factory = Factory()
    controller = MaintenanceResidentParentSupervisor(
        cfg, state_root=tmp_path / "parent", adapter_factory=child_factory,
        commissioned_config_path=config_path)
    assert child_factory.children[0].environment[parent.PARENT_CONFIG_PATH_ENV] == str(config_path)
    assert controller._spec["environment"][parent.PARENT_CONFIG_PATH_ENV] == str(config_path)
    _simulate_parent_process_exit(controller)


def test_parent_state_root_must_remain_owner_private(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("POSIX directory mode contract")
    cfg, _, _, _ = _fixture(tmp_path)
    root = tmp_path / "parent"
    root.mkdir(mode=0o755)
    root.chmod(0o755)
    with pytest.raises(ValueError, match="parent_supervision_state_root_not_private"):
        MaintenanceResidentParentSupervisor(cfg, state_root=root, adapter_factory=Factory())
    assert not (root / "parent-receipts.jsonl").exists()


def test_parent_custody_io_stays_bound_to_the_locked_directory(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("held directory descriptors require POSIX custody")
    controller, _child, _cfg = _parent(tmp_path)
    original_root = controller.root
    moved_root = tmp_path / "parent-original"
    original_root.rename(moved_root)
    original_root.mkdir(mode=0o700)

    controller._receipt("descriptor_bound_custody_probe")

    assert (moved_root / "parent-receipts.jsonl").exists()
    assert (moved_root / "parent-state.json").exists()
    assert not (original_root / "parent-receipts.jsonl").exists()
    assert not (original_root / "parent-state.json").exists()
    controller._release_owner_lock()


def test_exact_same_lineage_death_recovery_requires_readiness_and_links_receipts(tmp_path: Path) -> None:
    ready = [False]; controller, child, cfg = _parent(tmp_path, ready=ready)
    controller.start()
    assert child.alive and controller.status()["maintenance_eligible"] is False
    controller.observe()
    assert controller.status()["status"] == "awaiting_resident_readiness"
    ready[0] = True; controller.observe()
    first = controller.status()["launch_provenance_digest"]
    assert controller.status()["maintenance_eligible"] is True
    child.alive = False; ready[0] = False; controller.observe()
    assert child.starts == 2 and controller.status()["maintenance_eligible"] is False
    ready[0] = True; controller.observe()
    assert controller.status()["maintenance_eligible"] is True
    assert controller.status()["generation_digest"] and controller.status()["launch_provenance_digest"] != first
    rows = [json.loads(line) for line in (tmp_path / "parent/parent-receipts.jsonl").read_text().splitlines()]
    events = [row["event"] for row in rows]
    assert events.index("unexpected_child_death") < events.index("recovery_eligibility") < events.index("recovery_attempt")
    assert events[-2:] == ["child_resident_readiness", "recovery_success"]
    _simulate_parent_process_exit(controller)
    reconstructed = MaintenanceResidentParentSupervisor(cfg, state_root=tmp_path / "parent",
        resident_readiness_guard=lambda _: True, restart_budget=2, min_backoff=0, max_backoff=0,
        adapter_factory=Factory())
    assert reconstructed.status()["restart_count"] == 1


@pytest.mark.parametrize("wrong", ["argv", "cwd"])
def test_exact_child_spec_mismatch_fails_closed(tmp_path: Path, wrong: str) -> None:
    controller, _, _ = _parent(tmp_path, factory=Factory(wrong))
    with pytest.raises(ValueError, match="exact_child_identity_mismatch"): controller.start()
    assert controller.status()["maintenance_eligible"] is False


def test_corrupt_and_incomplete_transition_custody_deny_recovery(tmp_path: Path) -> None:
    for name, corrupt in (("corrupt", True), ("pending", False)):
        root = tmp_path / name; root.mkdir()
        controller, child, cfg = _parent(root, ready=[True]); controller.start(); controller.observe()
        journal = Path(str(cfg["transition_journal_path"]))
        if corrupt: journal.write_text("not-json\n")
        else: _journal_prefix(cfg, 1)
        child.alive = False; controller.observe()
        assert child.starts == 1 and controller.status()["maintenance_eligible"] is False


def test_readiness_absence_never_resumes_maintenance(tmp_path: Path) -> None:
    controller, _, _ = _parent(tmp_path, ready=[False]); controller.start()
    for _ in range(3): controller.observe()
    assert controller.status()["status"] == "awaiting_resident_readiness"
    assert controller.status()["maintenance_eligible"] is False


def test_budget_panic_shutdown_and_reconstruction_prevent_resurrection(tmp_path: Path) -> None:
    controller, child, cfg = _parent(tmp_path, ready=[True], budget=1)
    controller.start(); controller.observe(); child.alive = False; controller.observe()
    child.alive = False; controller.observe()
    assert controller.status()["restart_budget_exhausted"] is True and child.starts == 2
    _simulate_parent_process_exit(controller)
    made = Factory(); rebuilt = MaintenanceResidentParentSupervisor(cfg, state_root=tmp_path / "parent",
        resident_readiness_guard=lambda _: True, restart_budget=1, min_backoff=0, max_backoff=0,
        adapter_factory=made)
    rebuilt.observe(); assert made.children[0].starts == 0

    panic_root = tmp_path / "panic"; panic_root.mkdir()
    panic, panic_child, _ = _parent(panic_root, ready=[True]); panic.start(); panic.shutdown(panic=True)
    panic.observe(); assert panic_child.starts == 1 and panic.status()["panic_latched"] is True
    with pytest.raises(RuntimeError, match="panic_latched"): panic.start()

    stop_root = tmp_path / "stop"; stop_root.mkdir()
    stopped, stopped_child, _ = _parent(stop_root, ready=[True]); stopped.start(); stopped.shutdown()
    stopped.observe(); assert stopped_child.starts == 1 and stopped.status()["shutdown_latched"] is True


def test_persisted_provenance_or_configuration_mismatch_fails_closed(tmp_path: Path) -> None:
    controller, _, cfg = _parent(tmp_path); controller.start()
    state = tmp_path / "parent/parent-state.json"; value = json.loads(state.read_text())
    value["child_spec_digest"] = "sha256:foreign"; state.write_text(json.dumps(value))
    _simulate_parent_process_exit(controller)
    rebuilt = MaintenanceResidentParentSupervisor(cfg, state_root=tmp_path / "parent",
        resident_readiness_guard=lambda _: True, adapter_factory=Factory())
    assert rebuilt.status()["panic_latched"] is True
    with pytest.raises(RuntimeError, match="panic_latched"): rebuilt.start()


def test_invalid_state_recovery_does_not_append_duplicate_parent_receipt(
    tmp_path: Path,
) -> None:
    controller, _, _ = _parent(tmp_path)
    controller.start()
    receipt_path = tmp_path / "parent" / "parent-receipts.jsonl"
    before = receipt_path.read_bytes()
    state_path = tmp_path / "parent" / "parent-state.json"
    state_path.write_bytes(b"not-json\n")

    _simulate_parent_process_exit(controller)
    rebuilt, child, _ = _parent(tmp_path)
    assert rebuilt.status()["panic_latched"] is True
    assert receipt_path.read_bytes() == before
    with pytest.raises(RuntimeError, match="panic_latched"):
        rebuilt.start()
    assert child.starts == 0


def test_parent_state_symlink_is_untrusted_and_not_republished(tmp_path: Path) -> None:
    controller, _, _ = _parent(tmp_path)
    controller.start()
    receipt_path = tmp_path / "parent" / "parent-receipts.jsonl"
    before = receipt_path.read_bytes()
    state_path = tmp_path / "parent" / "parent-state.json"
    state_path.unlink()
    target = tmp_path / "foreign-state.json"
    target.write_text("{}", encoding="utf-8")
    state_path.symlink_to(target)

    _simulate_parent_process_exit(controller)
    rebuilt, _, _ = _parent(tmp_path)
    assert rebuilt.status()["panic_latched"] is True
    assert receipt_path.read_bytes() == before


def test_receipt_ahead_of_snapshot_is_rejected_without_sequence_reuse(tmp_path: Path) -> None:
    controller, _, _ = _parent(tmp_path)
    state_path = tmp_path / "parent" / "parent-state.json"
    previous_snapshot = state_path.read_bytes()
    controller.start()
    receipt_path = tmp_path / "parent" / "parent-receipts.jsonl"
    receipt_log = receipt_path.read_bytes()
    state_path.write_bytes(previous_snapshot)

    _simulate_parent_process_exit(controller)
    rebuilt, child, _ = _parent(tmp_path)
    assert rebuilt.status()["panic_latched"] is True
    assert rebuilt.status()["status"] == "fail_closed_state"
    assert receipt_path.read_bytes() == receipt_log
    with pytest.raises(RuntimeError, match="panic_latched"):
        rebuilt.start()
    assert child.starts == 0


def test_corrupt_receipt_chain_fails_closed_without_republication(tmp_path: Path) -> None:
    controller, _, _ = _parent(tmp_path)
    controller.start()
    receipt_path = tmp_path / "parent" / "parent-receipts.jsonl"
    rows = [json.loads(line) for line in receipt_path.read_bytes().splitlines()]
    rows[0]["receipt_digest"] = "sha256:" + "0" * 64
    corrupt = b"\n".join(
        json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        for row in rows
    ) + b"\n"
    receipt_path.write_bytes(corrupt)

    _simulate_parent_process_exit(controller)
    rebuilt, _, _ = _parent(tmp_path)
    assert rebuilt.status()["panic_latched"] is True
    assert rebuilt.status()["status"] == "fail_closed_state"
    assert receipt_path.read_bytes() == corrupt


def test_parent_receipt_recovery_rejects_malformed_timestamp_without_republication(
    tmp_path: Path,
) -> None:
    from sentientos import maintenance_resident_parent_supervision as parent

    controller, _child, _cfg = _parent(tmp_path)
    receipt_path = tmp_path / "parent" / "parent-receipts.jsonl"
    rows = [json.loads(line) for line in receipt_path.read_bytes().splitlines()]
    rows[0]["timestamp"] = "not-a-timestamp"
    row = rows[0]
    row.pop("receipt_digest")
    row["receipt_digest"] = parent._digest(row)
    malformed = json.dumps(row, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    receipt_path.write_bytes(malformed)
    _simulate_parent_process_exit(controller)

    rebuilt, _, _ = _parent(tmp_path)
    assert rebuilt.status()["panic_latched"] is True
    assert rebuilt.status()["status"] == "fail_closed_state"
    assert receipt_path.read_bytes() == malformed


def test_restarted_parent_denies_launch_when_prior_child_pid_is_present(tmp_path: Path) -> None:
    first, child, cfg = _parent(tmp_path, process_presence_observer=lambda _: True)
    first.start()
    assert child.alive

    with pytest.raises(RuntimeError, match="parent_supervision_owner_already_held"):
        MaintenanceResidentParentSupervisor(cfg, state_root=tmp_path / "parent",
            resident_readiness_guard=lambda _: True, adapter_factory=Factory())
    _simulate_parent_process_exit(first)
    made = Factory()
    rebuilt = MaintenanceResidentParentSupervisor(cfg, state_root=tmp_path / "parent",
        resident_readiness_guard=lambda _: True, adapter_factory=made,
        process_presence_observer=lambda pid: True)
    with pytest.raises(RuntimeError, match="prior_child_process_unreconciled"):
        rebuilt.start()
    assert made.children[0].starts == 0
    assert rebuilt.status()["status"] == "prior_child_unreconciled"


def test_restarted_parent_recovers_only_after_prior_pid_is_absent(tmp_path: Path) -> None:
    first, child, cfg = _parent(tmp_path, process_presence_observer=lambda _: False)
    first.start()
    child.alive = False

    _simulate_parent_process_exit(first)
    made = Factory()
    rebuilt = MaintenanceResidentParentSupervisor(cfg, state_root=tmp_path / "parent",
        resident_readiness_guard=lambda _: True, adapter_factory=made,
        process_presence_observer=lambda pid: False)
    rebuilt.start()
    assert made.children[0].starts == 1
    assert rebuilt.status()["restart_count"] == 1
    rows = [json.loads(line) for line in
        (tmp_path / "parent" / "parent-receipts.jsonl").read_text().splitlines()]
    events = [row["event"] for row in rows]
    assert events.index("orphan_child_absence_reconciled") < events.index("recovery_attempt")


def test_restarted_parent_recovers_when_pid_is_reused_by_a_new_process_generation(
    tmp_path: Path,
) -> None:
    first, child, cfg = _parent(tmp_path,
        process_start_ticks_observer=lambda _pid: 100)
    first.start()
    assert first._launch is not None
    assert first._launch["child_linux_proc_start_ticks"] == 100
    child.alive = False

    state_root = tmp_path / "parent"
    from sentientos import maintenance_resident_parent_supervision as parent
    rows = parent._parse_parent_receipt_journal(
        (state_root / "parent-receipts.jsonl").read_bytes(), first._spec_digest)
    parent._validate_parent_state_snapshot(
        (state_root / "parent-state.json").read_bytes(),
        expected_spec_digest=first._spec_digest,
        expected_config_digest=str(first.config["config_digest"]), rows=rows)
    assert first.status()["panic_latched"] is False, first.status()

    _simulate_parent_process_exit(first)
    made = Factory()
    rebuilt = MaintenanceResidentParentSupervisor(cfg, state_root=state_root,
        resident_readiness_guard=lambda _: True, adapter_factory=made,
        process_presence_observer=lambda _pid: True,
        process_start_ticks_observer=lambda _pid: 200)
    assert rebuilt.status()["panic_latched"] is False, rebuilt.status()
    rebuilt.start()
    assert made.children[0].starts == 1
    assert rebuilt.status()["restart_count"] == 1
    rows = [json.loads(line) for line in
        (tmp_path / "parent" / "parent-receipts.jsonl").read_text().splitlines()]
    recovered = next(row for row in rows if row["event"] == "orphan_child_absence_reconciled")
    assert recovered["detail"]["process_termination_evidence"] == {
        "posture": "prior_process_generation_terminated_pid_reused",
        "prior_start_ticks": 100,
        "observed_start_ticks": 200,
    }


def test_restarted_parent_fails_closed_when_prior_process_generation_is_still_live(
    tmp_path: Path,
) -> None:
    first, child, cfg = _parent(tmp_path,
        process_start_ticks_observer=lambda _pid: 100)
    first.start()
    child.alive = False

    _simulate_parent_process_exit(first)
    made = Factory()
    rebuilt = MaintenanceResidentParentSupervisor(cfg, state_root=tmp_path / "parent",
        resident_readiness_guard=lambda _: True, adapter_factory=made,
        process_presence_observer=lambda _pid: False,
        process_start_ticks_observer=lambda _pid: 100)
    with pytest.raises(RuntimeError, match="prior_child_process_unreconciled"):
        rebuilt.start()
    assert made.children[0].starts == 0
    assert rebuilt.status()["status"] == "prior_child_unreconciled"



def test_parent_supervision_owner_lock_is_singleton(tmp_path: Path) -> None:
    controller, child, cfg = _parent(tmp_path)
    with pytest.raises(RuntimeError, match="parent_supervision_owner_already_held"):
        MaintenanceResidentParentSupervisor(cfg, state_root=tmp_path / "parent",
            resident_readiness_guard=lambda _: True, adapter_factory=Factory())
    assert child.starts == 0
    _simulate_parent_process_exit(controller)


def test_default_parent_readiness_verifies_child_owned_provenance(tmp_path: Path) -> None:
    from datetime import datetime, timezone

    cfg, _generation, _custody, _repository = _fixture(tmp_path)
    launch_time = datetime(2030, 1, 2, 0, 0, 0, tzinfo=timezone.utc).timestamp()
    controller = MaintenanceResidentParentSupervisor(
        cfg, state_root=tmp_path / "parent", clock=lambda: launch_time,
        min_backoff=0, max_backoff=0, adapter_factory=Factory())
    controller.start()
    child = controller._adapter
    observation = {
        "python_executable": cfg["python_executable"],
        "daemon_entrypoint": cfg["daemon_entrypoint"],
        "cwd": cfg["working_directory"],
        "argv": [cfg["python_executable"], "-m", cfg["daemon_module"]],
        "pid": child.identity["pid"],
        "startup_timestamp": "2030-01-02T00:00:01Z",
        "environment": {key: controller._environment.get(key) for key in (
            "PYTHONPATH", "PYTHONHOME", resident.TRANSITION_ENV, resident.CONFIG_ENV,
            resident.SUCCESSOR_CONFIG_ENV, resident.AUTO_CONFIG_ENV)},
    }
    resident.MaintenanceResidentRuntimeAdoptionController(
        cfg, process_observer=lambda: observation).capture_baseline()
    controller.observe()
    assert controller.status()["maintenance_eligible"] is True
    assert controller.status()["status"] == "maintenance_eligible"
    assert controller.status()["readiness_basis"] == "child_owned_launch_provenance"
    rows = [json.loads(line) for line in
        (tmp_path / "parent" / "parent-receipts.jsonl").read_text().splitlines()]
    readiness = next(row for row in rows if row["event"] == "child_resident_readiness")
    assert readiness["detail"]["child_provenance"]["process_instance_id"]
    assert readiness["detail"]["child_provenance"]["provenance_digest"]
    _simulate_parent_process_exit(controller)


def test_default_parent_readiness_rejects_substituted_child_provenance(tmp_path: Path) -> None:
    from datetime import datetime, timezone

    cfg, _generation, _custody, _repository = _fixture(tmp_path)
    launch_time = datetime(2030, 1, 2, 0, 0, 0, tzinfo=timezone.utc).timestamp()
    controller = MaintenanceResidentParentSupervisor(
        cfg, state_root=tmp_path / "parent", clock=lambda: launch_time,
        min_backoff=0, max_backoff=0, adapter_factory=Factory())
    controller.start()
    child = controller._adapter
    observation = {
        "python_executable": cfg["python_executable"],
        "daemon_entrypoint": cfg["daemon_entrypoint"],
        "cwd": cfg["working_directory"],
        "argv": [cfg["python_executable"], "-m", cfg["daemon_module"]],
        "pid": child.identity["pid"] + 1,
        "startup_timestamp": "2030-01-02T00:00:01Z",
        "environment": {key: controller._environment.get(key) for key in (
            "PYTHONPATH", "PYTHONHOME", resident.TRANSITION_ENV, resident.CONFIG_ENV,
            resident.SUCCESSOR_CONFIG_ENV, resident.AUTO_CONFIG_ENV)},
    }
    resident.MaintenanceResidentRuntimeAdoptionController(
        cfg, process_observer=lambda: observation).capture_baseline()
    controller.observe()
    assert controller.status()["maintenance_eligible"] is False
    assert controller.status()["status"] == "awaiting_resident_readiness"
    _simulate_parent_process_exit(controller)


def test_state_publication_failure_blocks_followup_receipts(tmp_path: Path) -> None:
    controller, _, _ = _parent(tmp_path)
    state_path = tmp_path / "parent" / "parent-state.json"
    receipt_path = tmp_path / "parent" / "parent-receipts.jsonl"
    previous_state = state_path.read_bytes()
    previous_receipts = receipt_path.read_bytes()

    def fail_atomic(_value: Any) -> None:
        raise OSError("simulated_state_publication_failure")

    controller._atomic = fail_atomic
    with pytest.raises(OSError, match="simulated_state_publication_failure"):
        controller._receipt("state_publication_failure_probe")
    after_failed_publication = receipt_path.read_bytes()
    assert after_failed_publication != previous_receipts
    assert state_path.read_bytes() == previous_state
    with pytest.raises(RuntimeError, match="parent_state_recovery_not_trusted"):
        controller._receipt("must_not_follow_uncertain_publication")
    assert receipt_path.read_bytes() == after_failed_publication


def test_missing_native_lock_refuses_before_parent_state_creation(tmp_path: Path, monkeypatch) -> None:
    cfg, _, _, _ = _fixture(tmp_path)
    root = tmp_path / "parent-without-lock"
    monkeypatch.setattr(
        "sentientos.maintenance_resident_parent_supervision.require_flock",
        lambda: (_ for _ in ()).throw(OSError("native_lock_unavailable")))
    with pytest.raises(OSError, match="native_lock_unavailable"):
        MaintenanceResidentParentSupervisor(cfg, state_root=root)
    assert not root.exists()


def test_receipt_events_bind_their_parent_process_instance(tmp_path: Path) -> None:
    controller, _, cfg = _parent(tmp_path)
    first_instance = controller.status()["parent_process_instance_id"]
    first_rows = [json.loads(line) for line in
        (tmp_path / "parent" / "parent-receipts.jsonl").read_text().splitlines()]
    assert first_rows[0]["event"] == "parent_startup"
    assert first_rows[0]["detail"]["parent_process_instance_id"] == first_instance
    assert first_rows[0]["detail"]["parent_process_identity_schema"] == (
        "sentientos.parent_process_attribution:v2")
    assert first_rows[0]["detail"]["parent_process_observation"][
        "linux_proc_start_ticks_posture"] in {
            "linux_procfs_starttime_field_22", "unavailable"}
    assert first_rows[0]["detail"]["parent_process_observation"]["process_id"] == os.getpid()

    _simulate_parent_process_exit(controller)
    rebuilt = MaintenanceResidentParentSupervisor(cfg, state_root=tmp_path / "parent",
        resident_readiness_guard=lambda _: True, adapter_factory=Factory())
    second_instance = rebuilt.status()["parent_process_instance_id"]
    assert second_instance != first_instance
    rows = [json.loads(line) for line in
        (tmp_path / "parent" / "parent-receipts.jsonl").read_text().splitlines()]
    assert rows[-1]["event"] == "parent_startup"
    assert rows[-1]["detail"]["parent_process_instance_id"] == second_instance
    assert all(row["detail"]["parent_process_instance_id"] == first_instance
        for row in rows[:-1])


def test_v1_parent_process_observation_remains_readable(tmp_path: Path) -> None:
    from sentientos import maintenance_resident_parent_supervision as parent

    _, _, _ = _parent(tmp_path)
    path = tmp_path / "parent" / "parent-receipts.jsonl"
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    observation = row["detail"]["parent_process_observation"]
    observation.pop("linux_proc_start_ticks")
    observation.pop("linux_proc_start_ticks_posture")
    row["detail"]["parent_process_identity_schema"] = (
        "sentientos.parent_process_attribution:v1")
    row["detail"]["parent_process_instance_id"] = parent._digest(observation)
    row.pop("receipt_digest", None)
    row["receipt_digest"] = parent._digest(row)
    encoded = (parent._canonical(row) + b"\n")
    parsed = parent._parse_parent_receipt_journal(
        encoded, row["child_spec_digest"])
    assert parsed[0]["detail"]["parent_process_identity_schema"] == (
        "sentientos.parent_process_attribution:v1")


def test_legacy_parent_receipts_without_process_identity_remain_readable(tmp_path: Path) -> None:
    controller, _, _ = _parent(tmp_path)
    path = tmp_path / "parent" / "parent-receipts.jsonl"
    row = json.loads(path.read_text().splitlines()[0])
    row["detail"].pop("parent_process_instance_id")
    row["detail"].pop("parent_process_observation")
    row["detail"].pop("parent_process_identity_schema")
    module = __import__(
        "sentientos.maintenance_resident_parent_supervision",
        fromlist=["_canonical", "_digest"])
    row.pop("receipt_digest", None)
    row["receipt_digest"] = module._digest(row)
    path.write_bytes(module._canonical(row) + b"\n")
    recovered = controller._read_receipt_journal()
    assert len(recovered) == 1
    assert "parent_process_instance_id" not in recovered[0]["detail"]


def test_receipt_recovery_rejects_process_id_not_bound_to_startup_observation(tmp_path: Path) -> None:
    controller, _, _ = _parent(tmp_path)
    path = tmp_path / "parent" / "parent-receipts.jsonl"
    row = json.loads(path.read_text().splitlines()[0])
    row["detail"]["parent_process_instance_id"] = "sha256:" + "0" * 64
    module = __import__(
        "sentientos.maintenance_resident_parent_supervision",
        fromlist=["_canonical", "_digest"])
    row.pop("receipt_digest", None)
    row["receipt_digest"] = module._digest(row)
    path.write_bytes(module._canonical(row) + b"\n")
    with pytest.raises(ValueError, match="parent_process_startup_observation_invalid"):
        controller._read_receipt_journal()


def test_current_receipt_cannot_drop_its_process_identity_field(tmp_path: Path) -> None:
    controller, _, _ = _parent(tmp_path)
    path = tmp_path / "parent" / "parent-receipts.jsonl"
    row = json.loads(path.read_text().splitlines()[0])
    row["detail"].pop("parent_process_instance_id")
    module = __import__(
        "sentientos.maintenance_resident_parent_supervision",
        fromlist=["_canonical", "_digest"])
    row.pop("receipt_digest", None)
    row["receipt_digest"] = module._digest(row)
    path.write_bytes(module._canonical(row) + b"\n")
    with pytest.raises(ValueError, match="parent_process_attribution_schema_invalid"):
        controller._read_receipt_journal()


def _commissioned_parent_fixture(tmp_path: Path) -> tuple[dict[str, Any], Path]:
    from tests.test_maintenance_initial_posix_resident_commissioning import (
        NOW, Kernel as CommissioningKernel, approval, fixture, launch, commissioning,
    )

    manifest = fixture(tmp_path)
    intent = commissioning.prepare_intent(manifest)
    commissioned = commissioning.commission(
        manifest, approval(intent), kernel=CommissioningKernel(),
        correlation_id="parent-lifecycle-observation", clock=lambda: NOW,
        launch_runner=launch,
        allow_synthetic_approval_for_tests=True,
    )
    assert commissioned["status"] == "initial_resident_commissioned"
    config_path = Path(str(manifest["custody_root"])) / "resident-adoption.json"
    verified = commissioning.verify_commissioned_resident_config(config_path)
    return verified["resident_config"], config_path


def test_parent_lifecycle_observation_binds_actual_parent_and_child_pid_receipts(
        tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("commissioned parent lifecycle custody requires POSIX")
    from sentientos import maintenance_resident_parent_supervision as parent

    cfg, config_path = _commissioned_parent_fixture(tmp_path)
    factory = Factory()
    supervisor = MaintenanceResidentParentSupervisor(
        cfg, state_root=Path(cfg["state_root"]) / "parent-supervision",
        adapter_factory=factory, commissioned_config_path=config_path)
    # This adapter fixture writes a real, digest-bound parent launch receipt
    # while the injected process-ID readers identify this test process.
    factory.children[-1].pid = os.getpid() - 1
    supervisor.start()
    reader = ResidentParentLifecycleEvidenceReader(
        config_path, parent_pid=os.getpid, child_pid=os.getpid)
    records = reader.world_state_records(observed_at="2030-01-02T00:00:01Z")
    assert len(records) == 1
    record = records[0]
    assert record["subject_kind"] == "resident_parent_lifecycle_history"
    assert record["observed_at"] == record["payload"]["parent_process_started_at"]
    assert record["staleness"] == "unknown"
    assert record["payload"]["child_pid"] == os.getpid()
    assert record["payload"]["launch_receipt_digest"]
    assert record["payload"]["event_time_posture"] == "verified_historical_receipt_time"
    assert record["payload"]["current_running_generation_proven"] is False
    assert record["payload"]["effect_authority"] is False
    _simulate_parent_process_exit(supervisor)


def test_parent_lifecycle_observation_rejects_unmatched_process_relationship(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if os.name != "posix":
        pytest.skip("commissioned parent lifecycle custody requires POSIX")
    from sentientos import maintenance_resident_parent_supervision as parent

    cfg, config_path = _commissioned_parent_fixture(tmp_path)
    # Model a same-PID parent replacement while retaining all commissioned PID
    # and launch-receipt bindings. Only the recorded procfs start tick differs.
    monkeypatch.setattr(parent, "_linux_process_start_ticks", lambda _: 17)
    factory = Factory()
    supervisor = MaintenanceResidentParentSupervisor(
        cfg, state_root=Path(cfg["state_root"]) / "parent-supervision",
        adapter_factory=factory, commissioned_config_path=config_path)
    factory.children[-1].pid = os.getpid() - 1
    supervisor.start()
    monkeypatch.setattr(parent, "_linux_process_start_ticks", lambda _: 18)
    reader = ResidentParentLifecycleEvidenceReader(
        config_path, parent_pid=os.getpid, child_pid=os.getpid)
    with pytest.raises(ValueError, match="parent_observation_kernel_process_start_mismatch"):
        reader.world_state_records(observed_at="2030-01-02T00:00:01Z")
    monkeypatch.setattr(parent, "_linux_process_start_ticks", lambda _: 17)
    reader = ResidentParentLifecycleEvidenceReader(
        config_path, parent_pid=lambda: os.getpid() + 1, child_pid=os.getpid)
    with pytest.raises(ValueError, match="parent_observation_process_relation_unverified"):
        reader.world_state_records(observed_at="2030-01-02T00:00:01Z")
    reader = ResidentParentLifecycleEvidenceReader(
        config_path, parent_pid=os.getpid, child_pid=lambda: os.getpid() + 1)
    with pytest.raises(ValueError, match="parent_observation_child_launch_unverified"):
        reader.world_state_records(observed_at="2030-01-02T00:00:01Z")
    _simulate_parent_process_exit(supervisor)
