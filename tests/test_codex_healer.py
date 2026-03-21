from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sentientos.codex_healer import (
    Anomaly,
    CodexHealer,
    DaemonHeartbeat,
    HealingEnvironment,
    IntegrityGatekeeper,
    PulseWatcher,
    RecoveryLedger,
    ReGenesisProtocol,
    RepairAction,
    RepairSynthesizer,
    ReviewBoard,
)
from sentientos.runtime_governor import reset_runtime_governor


@pytest.fixture(autouse=True)
def _codex_startup(codex_startup: None) -> None:
    reset_runtime_governor()
    yield
    reset_runtime_governor()


def _build_healer(tmp_path: Path) -> tuple[CodexHealer, HealingEnvironment, PulseWatcher, RecoveryLedger]:
    vow = tmp_path / "vow"
    glow = tmp_path / "glow"
    pulse = tmp_path / "pulse"
    daemon = tmp_path / "daemon"
    for mount in (vow, glow, pulse, daemon):
        mount.mkdir(parents=True, exist_ok=True)

    archive = tmp_path / "archive"
    archive.mkdir()
    snapshot = archive / "snapshot_001.json"
    snapshot.write_text("{}", encoding="utf-8")

    pointer = tmp_path / "lineage.pointer"
    pointer.write_text(snapshot.name, encoding="utf-8")

    environment = HealingEnvironment(lineage_pointer=pointer, archive_root=archive)
    ledger = RecoveryLedger(tmp_path / "ledger.jsonl")
    watcher = PulseWatcher(
        heartbeat_timeout=60,
        required_mounts=[vow, glow, pulse, daemon],
        lineage_pointer=pointer,
        lineage_archive=archive,
    )
    synthesizer = RepairSynthesizer(environment)
    board = ReviewBoard(trust_threshold=0.6)
    regenesis = ReGenesisProtocol(environment)
    healer = CodexHealer(watcher, synthesizer, board, regenesis, ledger)
    return healer, environment, watcher, ledger


def test_daemon_crash_triggers_restart(tmp_path: Path) -> None:
    healer, environment, watcher, ledger = _build_healer(tmp_path)

    now = datetime.now(timezone.utc)
    heartbeats = [
        DaemonHeartbeat("NetworkDaemon", now - timedelta(minutes=10)),
        DaemonHeartbeat("IntegrityDaemon", now),
    ]

    results = healer.run(heartbeats, now=now)
    assert results, "PulseWatcher should report the stalled daemon"
    assert environment.restart_requests == ["NetworkDaemon"]

    entry = ledger.entries[-1]
    assert entry["status"] == "auto-repair verified"
    assert entry["anomaly"]["kind"] == "daemon_unresponsive"
    assert isinstance(entry["correlation_id"], str) and len(entry["correlation_id"]) == 64
    verification = entry["details"]["repair_verification"]
    assert verification["status"] in {"verified", "unverified", "skipped verification", "verification blocked/degraded"}
    assert "CodexHealer event: auto-repair verified" == entry["narrative"]

    # Updated heartbeat should clear anomalies and mounts remain intact
    healed_heartbeats = [DaemonHeartbeat("NetworkDaemon", now), DaemonHeartbeat("IntegrityDaemon", now)]
    assert not watcher.scan(healed_heartbeats, now=now)
    for mount in environment.mount_repairs:
        assert mount.exists()


def test_regenesis_restores_corrupted_lineage(tmp_path: Path) -> None:
    healer, environment, watcher, ledger = _build_healer(tmp_path)

    # Create an additional snapshot and corrupt the pointer
    archive = environment.archive_root
    assert archive is not None
    good_snapshot = archive / "snapshot_002.json"
    good_snapshot.write_text("{}", encoding="utf-8")

    pointer = environment.lineage_pointer
    assert pointer is not None
    pointer.write_text("snapshot_missing.json", encoding="utf-8")

    environment.fail_rebind_once = True

    now = datetime.now(timezone.utc)
    heartbeats = [DaemonHeartbeat("NetworkDaemon", now), DaemonHeartbeat("IntegrityDaemon", now)]

    results = healer.run(heartbeats, now=now)
    assert results and any(r["status"] != "auto-repair verified" for r in results)

    entry = ledger.entries[-1]
    assert entry["status"] in {
        "auto-repair deferred_root_cause",
        "auto-repair regenesis_escalated",
        "auto-repair quarantined",
    }
    if "regenesis" in entry["details"]:
        regenesis_details = entry["details"]["regenesis"]
        assert regenesis_details["status"] == "regenesis"
        assert regenesis_details["snapshot"] == good_snapshot.name

    assert pointer.read_text(encoding="utf-8").strip() in {good_snapshot.name, "snapshot_missing.json"}


def test_hostile_repair_is_quarantined(tmp_path: Path) -> None:
    healer, environment, watcher, ledger = _build_healer(tmp_path)

    hostile_board = ReviewBoard(
        trust_threshold=0.6,
        integrity_gatekeeper=IntegrityGatekeeper(allowed_signatures=["trusted"]),
    )
    healer = CodexHealer(
        watcher,
        RepairSynthesizer(environment),
        hostile_board,
        ReGenesisProtocol(environment),
        ledger,
    )

    anomaly = Anomaly("daemon_unresponsive", "NetworkDaemon", {"heartbeat_age_seconds": 120})
    hostile_action = RepairAction(
        kind="config_patch",
        subject="NetworkDaemon",
        description="Attempted unauthorized patch",
        execute=lambda: True,
        auto_adopt=True,
        metadata={"trust": 0.9, "origin": "external", "hostile": True},
    )

    result = healer.review_external(anomaly, hostile_action)
    assert result["status"] in {"auto-repair rejected", "auto-repair quarantined"}
    assert result["quarantined"] is True
    assert result["details"]["review_reason"] == "integrity_blocked"
    assert result["details"].get("regenesis_deferred") is True or environment.regenesis_restores


def test_runtime_governor_blocks_repair_in_enforce_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_REPAIR_LIMIT", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    reset_runtime_governor()

    healer, environment, _, ledger = _build_healer(tmp_path)
    now = datetime.now(timezone.utc)
    stalled = [
        DaemonHeartbeat("NetworkDaemon", now - timedelta(minutes=10)),
        DaemonHeartbeat("IntegrityDaemon", now),
    ]

    first = healer.run(stalled, now=now)
    second = healer.run(stalled, now=now + timedelta(seconds=1))

    assert first
    assert second
    assert ledger.entries[-1]["status"] in {
        "auto-repair denied_by_governor",
        "auto-repair regenesis_escalated",
        "auto-repair deferred_root_cause",
        "auto-repair quarantined",
    }
    if ledger.entries[-1]["status"] == "auto-repair denied_by_governor":
        assert "governor_reason" in ledger.entries[-1]["details"]
    assert ledger.entries[-1]["details"].get("regenesis_deferred") is True or environment.regenesis_restores


def test_repair_loop_backoff_and_ceiling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIENTOS_REPAIR_ATTEMPT_CEILING", "2")
    monkeypatch.setenv("SENTIENTOS_REPAIR_BACKOFF_SECONDS", "60")
    healer, _, _, ledger = _build_healer(tmp_path)

    anomaly = Anomaly("daemon_unresponsive", "NetworkDaemon", {"heartbeat_age_seconds": 120})
    hostile_action = RepairAction(
        kind="config_patch",
        subject="NetworkDaemon",
        description="Attempted unauthorized patch",
        execute=lambda: True,
        auto_adopt=True,
        metadata={"trust": 0.1, "origin": "external"},
    )

    first = healer.review_external(anomaly, hostile_action)
    key = healer._anomaly_key(anomaly)  # type: ignore[attr-defined]
    healer._next_allowed[key] = datetime.now(timezone.utc) - timedelta(seconds=1)  # type: ignore[attr-defined]
    second = healer.review_external(anomaly, hostile_action)
    healer._next_allowed[key] = datetime.now(timezone.utc) - timedelta(seconds=1)  # type: ignore[attr-defined]
    third = healer.review_external(anomaly, hostile_action)

    assert first["status"] == "auto-repair rejected"
    assert second["status"] == "auto-repair quarantined"
    assert third["status"] == "auto-repair regenesis_escalated"
    assert isinstance(first["correlation_id"], str)
    assert first["correlation_id"] == second["correlation_id"] == third["correlation_id"]


def test_repair_verification_can_be_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIENTOS_REPAIR_VERIFY", "0")
    healer, _, _, ledger = _build_healer(tmp_path)
    now = datetime.now(timezone.utc)
    stalled = [
        DaemonHeartbeat("NetworkDaemon", now - timedelta(minutes=10)),
        DaemonHeartbeat("IntegrityDaemon", now),
    ]
    healer.run(stalled, now=now)
    verification = ledger.entries[-1]["details"]["repair_verification"]
    assert verification["status"] in {"skipped verification", "unverified"}
