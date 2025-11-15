import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import pytest

from sentientos.cathedral import Amendment
from sentientos.runtime.shell import DEFAULT_RUNTIME_CONFIG, RuntimeShell


def _build_runtime_config(tmp_path: Path) -> Dict[str, object]:
    runtime_root = tmp_path / "SentientOS"
    data_dir = runtime_root / "sentientos_data"
    models_dir = data_dir / "models"
    config_dir = data_dir / "config"
    logs_dir = runtime_root / "logs"
    cathedral_dir = runtime_root / "cathedral"
    rollback_dir = cathedral_dir / "rollback"
    for directory in (models_dir, config_dir, logs_dir, cathedral_dir, rollback_dir):
        directory.mkdir(parents=True, exist_ok=True)
    config = {
        "runtime": {
            **DEFAULT_RUNTIME_CONFIG,
            "root": str(runtime_root),
            "logs_dir": str(logs_dir),
            "data_dir": str(data_dir),
            "models_dir": str(models_dir),
            "config_dir": str(config_dir),
            "watchdog_interval": 0.01,
        },
        "persona": {
            "enabled": True,
            "tick_interval_seconds": 30,
            "max_message_length": 180,
        },
        "cathedral": {
            "review_log": str(runtime_root / "review.log"),
            "quarantine_dir": str(runtime_root / "quarantine"),
            "ledger_path": str(cathedral_dir / "ledger.jsonl"),
            "rollback_dir": str(rollback_dir),
        },
    }
    (config_dir / "runtime.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config


def test_auto_revert_triggers_rollback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = _build_runtime_config(tmp_path)

    monkeypatch.setattr("sentientos.cathedral.review.evaluate_invariants", lambda amendment: [])
    monkeypatch.setattr(
        "sentientos.runtime.shell.evaluate_invariants", lambda amendment: ["post_apply_failure"]
    )

    events: List[Dict[str, object]] = []
    monkeypatch.setattr(
        "sentientos.runtime.shell.publish_event",
        lambda payload: events.append(dict(payload)),
    )

    shell = RuntimeShell(config)
    notifications: List[str] = []
    shell.register_dashboard_notifier(notifications.append)
    spoken: List[str] = []
    shell._speak_callback = lambda message: spoken.append(message)  # type: ignore[assignment]

    amendment = Amendment(
        id="auto-revert",
        created_at=datetime(2024, 7, 1, 12, 0, tzinfo=timezone.utc),
        proposer="tester",
        summary="Adjust watchdog",
        changes={"config": {"runtime": {"watchdog_interval": 0.02}}},
        reason="Runtime tuning",
    )

    result = shell.submit_amendment(amendment)

    assert result.status == "accepted"
    assert shell.cathedral_digest.rollbacks == 1
    assert shell.cathedral_digest.auto_reverts == 1
    assert shell.cathedral_digest.last_reverted_id == "auto-revert"
    assert shell.cathedral_digest.last_quarantined_id == "auto-revert"
    assert shell.cathedral_digest.last_quarantine_error == "post_apply_failure"

    assert any("Auto-reverted" in message for message in notifications)
    assert any(message.startswith("Initiating rollback") for message in notifications)
    assert notifications[-1].startswith("Rollback complete")

    assert spoken and spoken[-1] == "A change violated system integrity. I reverted to a safe state."

    assert events and events[-1]["event"] == "rollback"
    assert events[-1]["amendment_id"] == "auto-revert"

    config_path = Path(config["runtime"]["config_dir"]) / "runtime.json"  # type: ignore[index]
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["runtime"]["watchdog_interval"] == pytest.approx(0.01)
