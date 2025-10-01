from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

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
    assert entry["status"] == "auto-repair applied"
    assert entry["anomaly"]["kind"] == "daemon_unresponsive"
    assert "CodexHealer event: auto-repair applied" == entry["narrative"]

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
    assert results and any(r["status"] != "auto-repair applied" for r in results)

    entry = ledger.entries[-1]
    assert entry["status"] == "auto-repair escalated"
    regenesis_details = entry["details"]["regenesis"]
    assert regenesis_details["status"] == "regenesis"
    assert regenesis_details["snapshot"] == good_snapshot.name

    assert pointer.read_text(encoding="utf-8").strip() == good_snapshot.name
    assert environment.regenesis_restores == [good_snapshot]


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
    assert result["status"] == "auto-repair rejected"
    assert result["quarantined"] is True
    assert result["details"]["review_reason"] == "integrity_blocked"
    assert environment.regenesis_restores, "ReGenesis should have been invoked"

