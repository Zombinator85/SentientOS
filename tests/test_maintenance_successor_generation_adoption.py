from pathlib import Path
from datetime import datetime, timezone

import pytest

from sentientos import maintenance_successor_generation_adoption as adoption

pytestmark = pytest.mark.no_legacy_skip


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
