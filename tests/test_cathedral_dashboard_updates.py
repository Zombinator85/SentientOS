import json
from pathlib import Path
from typing import Dict, List

from sentientos.persona import initial_state
from sentientos.persona.loop import PersonaLoop
from sentientos.runtime.shell import DEFAULT_RUNTIME_CONFIG, RuntimeShell


def _prepare_runtime(tmp_path: Path) -> Dict[str, object]:
    runtime_root = tmp_path / "SentientOS"
    data_dir = runtime_root / "sentientos_data"
    config_dir = data_dir / "config"
    logs_dir = runtime_root / "logs"
    cathedral_dir = runtime_root / "cathedral"
    rollback_dir = cathedral_dir / "rollback"
    for directory in (config_dir, logs_dir, cathedral_dir, rollback_dir):
        directory.mkdir(parents=True, exist_ok=True)
    config = {
        "runtime": {
            **DEFAULT_RUNTIME_CONFIG,
            "root": str(runtime_root),
            "config_dir": str(config_dir),
            "logs_dir": str(logs_dir),
            "watchdog_interval": 0.2,
        },
        "cathedral": {
            "review_log": str(runtime_root / "review.log"),
            "quarantine_dir": str(runtime_root / "quarantine"),
            "ledger_path": str(cathedral_dir / "ledger.jsonl"),
            "rollback_dir": str(rollback_dir),
        },
        "persona": {"enabled": True, "tick_interval_seconds": 30, "max_message_length": 180},
    }
    (config_dir / "runtime.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config


def _install_metadata(config: Dict[str, object], amendment_id: str, previous: float, value: float) -> None:
    cathedral_cfg = config["cathedral"]  # type: ignore[index]
    ledger_path = Path(cathedral_cfg["ledger_path"])  # type: ignore[index]
    rollback_dir = Path(cathedral_cfg["rollback_dir"])  # type: ignore[index]
    digest = f"digest-{amendment_id}"
    ledger_entry = {
        "ts": "2024-07-01T01:00:00Z",
        "amendment_id": amendment_id,
        "digest": digest,
        "applied": {
            "config": {
                "runtime": {
                    "watchdog_interval": {"previous": previous, "value": value}
                }
            }
        },
    }
    ledger_path.write_text(json.dumps(ledger_entry) + "\n", encoding="utf-8")
    metadata = {
        "original": {"config": {"runtime": {"watchdog_interval": previous}}},
        "applied": ledger_entry["applied"],
        "digest": digest,
    }
    rollback_dir.mkdir(parents=True, exist_ok=True)
    (rollback_dir / f"{amendment_id}.json").write_text(json.dumps(metadata), encoding="utf-8")


def test_manual_rollback_updates_dashboard(monkeypatch, tmp_path: Path) -> None:
    config = _prepare_runtime(tmp_path)
    config["runtime"]["watchdog_interval"] = 0.3  # type: ignore[index]
    amendment_id = "manual-rollback"
    _install_metadata(config, amendment_id, previous=0.2, value=0.3)

    events: List[Dict[str, object]] = []
    monkeypatch.setattr(
        "sentientos.runtime.shell.publish_event",
        lambda payload: events.append(dict(payload)),
    )

    shell = RuntimeShell(config)
    notifications: List[str] = []
    shell.register_dashboard_notifier(notifications.append)

    shell.rollback(amendment_id, reason="Manual test")

    assert shell.cathedral_digest.rollbacks == 1
    assert shell.cathedral_digest.auto_reverts == 0
    assert shell.cathedral_digest.last_reverted_id == amendment_id

    assert any(message.startswith("Initiating rollback") for message in notifications)
    assert notifications[-1].startswith("Rollback complete")

    assert events and events[-1]["event"] == "rollback"

    config_path = Path(config["runtime"]["config_dir"]) / "runtime.json"  # type: ignore[index]
    restored = json.loads(config_path.read_text(encoding="utf-8"))
    assert restored["runtime"]["watchdog_interval"] == 0.2


def test_persona_summary_mentions_recent_rollback() -> None:
    loop = PersonaLoop(initial_state())
    message = loop._build_summary([{"kind": "cathedral", "event": "rollback"}])
    assert message == "I detected an inconsistency and restored my previous stable configuration."
