from __future__ import annotations

import json
from pathlib import Path

from sentientos.integrity_pressure import IntegrityPressureMetrics, IntegrityPressureSnapshot
from sentientos.orchestrator import OrchestratorConfig, tick
from sentientos.schema_registry import SchemaName, latest_version


def _seed_repo(root: Path) -> None:
    (root / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (root / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")


def test_tick_writes_report_and_pulse(tmp_path: Path) -> None:
    _seed_repo(tmp_path)

    result = tick(tmp_path, config=OrchestratorConfig(True, 300, False, False, False, False))

    report_path = tmp_path / result.tick_report_path
    assert report_path.exists()
    rows = [json.loads(line) for line in (tmp_path / "pulse/orchestrator_ticks.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows
    assert rows[-1]["tick_report_path"] == result.tick_report_path


def test_tick_updates_index_fields(tmp_path: Path) -> None:
    _seed_repo(tmp_path)

    tick(tmp_path, config=OrchestratorConfig(True, 300, False, False, False, False))

    payload = json.loads((tmp_path / "glow/forge/index.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == latest_version(SchemaName.FORGE_INDEX)
    assert payload["orchestrator_enabled"] is True
    assert payload["last_orchestrator_tick_status"] in {"ok", "warning", "failed", "unknown"}
    assert isinstance(payload["orchestrator_backlog_summary"], dict)
    assert payload["last_tick_report_path"]


def test_tick_respects_quarantine_for_mutation(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _seed_repo(tmp_path)
    (tmp_path / "glow/forge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/quarantine.json").write_text(json.dumps({"schema_version": 1, "active": True, "freeze_forge": True}) + "\n", encoding="utf-8")

    called = {"auto": 0}

    def _fake_auto(*args: object, **kwargs: object) -> object:
        called["auto"] += 1
        raise AssertionError("auto remediation should not run under quarantine")

    monkeypatch.setattr("sentientos.orchestrator.maybe_auto_run_pack", _fake_auto)

    tick(tmp_path, config=OrchestratorConfig(True, 300, False, True, False, True))

    assert called["auto"] == 0


def test_tick_auto_remediation_respects_cooldown_and_attempts(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _seed_repo(tmp_path)
    monkeypatch.setenv("SENTIENTOS_AUTO_REMEDIATION_COOLDOWN_MINUTES", "60")
    monkeypatch.setenv("SENTIENTOS_AUTO_REMEDIATION_MAX_ATTEMPTS", "1")

    pack_payload = {
        "schema_version": 1,
        "pack_id": "pack_1",
        "steps": [{"name": "verify", "allowlisted": True, "destructive": False}],
    }
    (tmp_path / "glow/forge/remediation/packs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/remediation/packs/pack_pack_1.json").write_text(json.dumps(pack_payload) + "\n", encoding="utf-8")
    (tmp_path / "pulse").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pulse/remediation_packs.jsonl").write_text(
        json.dumps({"pack_id": "pack_1", "pack_path": "glow/forge/remediation/packs/pack_pack_1.json", "status": "queued", "incident_id": "inc-1"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "pulse/auto_remediation_attempts.jsonl").write_text(
        json.dumps({"pack_id": "pack_1", "incident_id": "inc-1", "attempted_at": "2099-01-01T00:00:00Z"}) + "\n",
        encoding="utf-8",
    )

    snapshot = IntegrityPressureSnapshot(
        level=2,
        metrics=IntegrityPressureMetrics(incidents_last_1h=0, incidents_last_24h=0, enforced_failures_last_24h=0, unique_trigger_types_last_24h=0, quarantine_activations_last_24h=0),
        warn_threshold=1,
        enforce_threshold=2,
        critical_threshold=3,
        strategic_posture="balanced",
        checked_at="2099-01-01T00:00:00Z",
    )
    monkeypatch.setattr("sentientos.orchestrator.compute_integrity_pressure", lambda _root: snapshot)

    result = tick(tmp_path, config=OrchestratorConfig(True, 300, False, True, False, False))

    assert result.remediation_status in {"cooldown", "failed"}


def test_tick_emits_federation_snapshot(tmp_path: Path) -> None:
    _seed_repo(tmp_path)

    tick(tmp_path, config=OrchestratorConfig(True, 300, False, False, True, False))

    assert (tmp_path / "glow/federation/integrity_snapshot.json").exists()
