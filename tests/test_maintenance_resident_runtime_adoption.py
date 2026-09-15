import json
from pathlib import Path

import pytest

from sentientos import maintenance_resident_runtime_adoption as resident

pytestmark = pytest.mark.no_legacy_skip


def config(tmp_path: Path, **changes: object) -> dict[str, object]:
    root = tmp_path.resolve(); python = Path(__import__("sys").executable).resolve()
    value: dict[str, object] = {"schema_version": resident.CONFIG_SCHEMA, "enabled": True,
        "continuity_policy_path": str(root / "continuity.json"), "continuity_policy_digest": "sha256:c",
        "successor_adoption_config_path": str(root / "successor.json"), "successor_adoption_config_digest": "sha256:s",
        "automatic_continuity_config_path": "", "automatic_continuity_config_digest": "",
        "repository_identity": "repo", "repository_root": str(root), "python_executable": str(python),
        "daemon_module": "sentientosd", "daemon_entrypoint": str(root / "sentientosd.py"),
        "working_directory": str(root), "inherited_environment_allowlist": ["PATH"],
        "required_environment": {resident.CONFIG_ENV: str(root / "resident.json")}, "state_root": str(root / "state"),
        "transition_journal_path": str(root / "state" / "transitions.jsonl"), "provenance_root": str(root / "state" / "provenance"),
        "receipt_root": str(root / "state" / "receipts"), "stop_marker": str(root / "state" / "STOP"),
        "quiescence_timeout_seconds": 2, "readiness_timeout_seconds": 2, "maximum_successful_transitions": 2,
        "maximum_wall_clock_seconds": 20, "config_digest": ""}
    value.update(changes); value["config_digest"] = resident.digest(value, "config_digest"); return value


def handoff() -> dict[str, object]:
    return {"lineage_id": "lineage", "predecessor_ordinal": 0, "predecessor_generation_digest": "sha256:n0",
        "successor_ordinal": 1, "successor_generation_digest": "sha256:n1", "continuity_receipt_digest": "sha256:r1",
        "pending_handoff_event_digest": "sha256:h1", "predecessor_quiescence_confirmed": True,
        "successor_start_attempted": False}


def test_real_config_validation_and_closed_environment(tmp_path: Path) -> None:
    assert resident.validate_config(config(tmp_path))["enabled"] is True
    with pytest.raises(ValueError, match="unbound_interpreter_environment"):
        resident.validate_config(config(tmp_path, inherited_environment_allowlist=["PYTHONPATH"]))


def test_exact_exec_plan_and_post_exec_readiness_recovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = config(tmp_path); calls: list[tuple[str, list[str], object]] = []
    controller = resident.MaintenanceResidentRuntimeAdoptionController(cfg, execve=lambda e, a, v: calls.append((e, a, v)))
    result = controller.request_replacement(handoff())
    assert calls[0][1] == [cfg["python_executable"], "-m", "sentientosd"]
    assert not controller.readiness_guard(handoff())
    controller.complete_post_exec(handoff(), result["transition_id"])
    assert controller.readiness_guard(handoff())


def test_exec_failure_and_stop_are_fail_closed(tmp_path: Path) -> None:
    cfg = config(tmp_path); Path(cfg["stop_marker"]).parent.mkdir(); Path(cfg["stop_marker"]).touch()
    controller = resident.MaintenanceResidentRuntimeAdoptionController(cfg)
    with pytest.raises(ValueError, match="paused"): controller.request_replacement(handoff())
    Path(cfg["stop_marker"]).unlink()
    controller = resident.MaintenanceResidentRuntimeAdoptionController(cfg, execve=lambda *_: (_ for _ in ()).throw(OSError("no")))
    with pytest.raises(OSError): controller.request_replacement(handoff())
    assert controller.health()["status"] == "blocked"
