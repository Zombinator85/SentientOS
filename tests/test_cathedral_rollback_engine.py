import json
from pathlib import Path

from sentientos.cathedral.rollback import RollbackEngine


def _runtime_config(base_dir: Path) -> dict[str, object]:
    config_dir = base_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    runtime_section = {
        "root": str(base_dir),
        "config_dir": str(config_dir),
    }
    config = {
        "runtime": runtime_section,
        "persona": {"tick_interval_seconds": 42},
    }
    (config_dir / "runtime.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config


def _ledger_entry(amendment_id: str, digest: str, *, previous: int, value: int) -> dict[str, object]:
    return {
        "ts": "2024-07-01T00:00:00Z",
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


def test_revert_valid_metadata(tmp_path: Path) -> None:
    base_dir = tmp_path / "SentientOS"
    config = _runtime_config(base_dir)
    ledger_path = base_dir / "ledger.jsonl"
    rollback_dir = base_dir / "rollback"
    rollback_dir.mkdir(parents=True, exist_ok=True)

    amendment_id = "amend-1"
    digest = "digest-123"
    ledger_entry = _ledger_entry(amendment_id, digest, previous=5, value=7)
    ledger_path.write_text(json.dumps(ledger_entry) + "\n", encoding="utf-8")

    metadata = {
        "original": {"config": {"runtime": {"watchdog_interval": 5}}},
        "applied": ledger_entry["applied"],
        "digest": digest,
    }
    (rollback_dir / f"{amendment_id}.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    config["runtime"]["watchdog_interval"] = 7  # type: ignore[index]

    engine = RollbackEngine(config, rollback_dir, ledger_path)
    result = engine.revert(amendment_id)

    assert result.status == "success"
    assert result.reverted["config"]["runtime"]["watchdog_interval"]["restored"] == 5
    assert engine.runtime_config["runtime"]["watchdog_interval"] == 5  # type: ignore[index]

    persisted = json.loads((Path(config["runtime"]["config_dir"]) / "runtime.json").read_text(encoding="utf-8"))  # type: ignore[index]
    assert persisted["runtime"]["watchdog_interval"] == 5

    ledger_lines = ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(ledger_lines) == 2
    last_entry = json.loads(ledger_lines[-1])
    assert last_entry["event"] == "rollback"
    assert last_entry["auto_revert"] is False


def test_revert_digest_mismatch(tmp_path: Path) -> None:
    base_dir = tmp_path / "SentientOS"
    config = _runtime_config(base_dir)
    ledger_path = base_dir / "ledger.jsonl"
    rollback_dir = base_dir / "rollback"
    rollback_dir.mkdir(parents=True, exist_ok=True)

    amendment_id = "amend-digest"
    ledger_path.write_text(json.dumps(_ledger_entry(amendment_id, "digest-a", previous=1, value=2)) + "\n", encoding="utf-8")

    metadata = {
        "original": {"config": {"runtime": {"watchdog_interval": 1}}},
        "applied": {},
        "digest": "digest-b",
    }
    (rollback_dir / f"{amendment_id}.json").write_text(json.dumps(metadata), encoding="utf-8")

    engine = RollbackEngine(config, rollback_dir, ledger_path)
    result = engine.revert(amendment_id)

    assert result.status == "error"
    assert "digest" in result.errors

    ledger_lines = ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(ledger_lines[-1])["event"] == "rollback_error"


def test_revert_forbidden_domain(tmp_path: Path) -> None:
    base_dir = tmp_path / "SentientOS"
    config = _runtime_config(base_dir)
    ledger_path = base_dir / "ledger.jsonl"
    rollback_dir = base_dir / "rollback"
    rollback_dir.mkdir(parents=True, exist_ok=True)

    amendment_id = "amend-os"
    digest = "digest-os"
    ledger_path.write_text(json.dumps(_ledger_entry(amendment_id, digest, previous=1, value=2)) + "\n", encoding="utf-8")

    metadata = {
        "original": {"system": {"mode": "unsafe"}},
        "applied": {},
        "digest": digest,
    }
    (rollback_dir / f"{amendment_id}.json").write_text(json.dumps(metadata), encoding="utf-8")

    engine = RollbackEngine(config, rollback_dir, ledger_path)
    result = engine.revert(amendment_id)

    assert result.status == "error"
    assert "system" in result.errors


def test_revert_partial_when_path_missing(tmp_path: Path) -> None:
    base_dir = tmp_path / "SentientOS"
    config = _runtime_config(base_dir)
    config["runtime"]["watchdog_interval"] = 4  # type: ignore[index]
    ledger_path = base_dir / "ledger.jsonl"
    rollback_dir = base_dir / "rollback"
    rollback_dir.mkdir(parents=True, exist_ok=True)

    amendment_id = "amend-partial"
    digest = "digest-partial"
    ledger_entry = _ledger_entry(amendment_id, digest, previous=4, value=6)
    ledger_path.write_text(json.dumps(ledger_entry) + "\n", encoding="utf-8")

    metadata = {
        "original": {
            "config": {"runtime": {"watchdog_interval": 4}},
            "world": {"sources": {"news": True}},
        },
        "applied": ledger_entry["applied"],
        "digest": digest,
    }
    (rollback_dir / f"{amendment_id}.json").write_text(json.dumps(metadata), encoding="utf-8")

    engine = RollbackEngine(config, rollback_dir, ledger_path)
    result = engine.revert(amendment_id)

    assert result.status == "partial"
    assert "world.sources.news" in result.errors
    assert engine.runtime_config["runtime"]["watchdog_interval"] == 4  # type: ignore[index]


def test_revert_updates_config_atomically(tmp_path: Path) -> None:
    base_dir = tmp_path / "SentientOS"
    config = _runtime_config(base_dir)
    config["runtime"]["watchdog_interval"] = 9  # type: ignore[index]
    ledger_path = base_dir / "ledger.jsonl"
    rollback_dir = base_dir / "rollback"
    rollback_dir.mkdir(parents=True, exist_ok=True)

    amendment_id = "amend-atomic"
    digest = "digest-atomic"
    ledger_entry = _ledger_entry(amendment_id, digest, previous=3, value=9)
    ledger_path.write_text(json.dumps(ledger_entry) + "\n", encoding="utf-8")

    metadata = {
        "original": {"config": {"runtime": {"watchdog_interval": 3}}},
        "applied": ledger_entry["applied"],
        "digest": digest,
    }
    (rollback_dir / f"{amendment_id}.json").write_text(json.dumps(metadata), encoding="utf-8")

    engine = RollbackEngine(config, rollback_dir, ledger_path)
    engine.revert(amendment_id)

    config_path = Path(config["runtime"]["config_dir"]) / "runtime.json"  # type: ignore[index]
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["runtime"]["watchdog_interval"] == 3
    temp_files = [p for p in config_path.parent.iterdir() if p.name != "runtime.json"]
    assert temp_files == []
