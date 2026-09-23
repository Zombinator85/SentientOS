import json
from pathlib import Path
from typing import Any

import pytest

from sentientos import maintenance_resident_runtime_adoption as resident
from sentientos.maintenance_resident_parent_supervision import MaintenanceResidentParentSupervisor
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


def _parent(tmp_path: Path, *, ready: list[bool] | None = None, budget: int = 2,
            factory: Factory | None = None) -> tuple[MaintenanceResidentParentSupervisor, FakeChild, dict[str, object]]:
    cfg, _, _, _ = _fixture(tmp_path)
    readiness = ready if ready is not None else [False]
    made = factory or Factory()
    controller = MaintenanceResidentParentSupervisor(cfg, state_root=tmp_path / "parent",
        resident_readiness_guard=lambda _: readiness[0], restart_budget=budget,
        min_backoff=0, max_backoff=0, adapter_factory=made)
    return controller, made.children[-1], cfg


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
    rebuilt = MaintenanceResidentParentSupervisor(cfg, state_root=tmp_path / "parent",
        resident_readiness_guard=lambda _: True, adapter_factory=Factory())
    assert rebuilt.status()["panic_latched"] is True
    with pytest.raises(RuntimeError, match="panic_latched"): rebuilt.start()
