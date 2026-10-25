from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sentientos.cathedral import Amendment
from sentientos.cathedral.apply import AmendmentApplicator
from sentientos.runtime import bootstrap


@pytest.fixture()
def runtime_config(tmp_path: Path) -> dict[str, object]:
    base_dir = tmp_path / "SentientOS"
    config = bootstrap.build_default_config(base_dir)
    runtime_section = config["runtime"]  # type: ignore[index]
    runtime_section["root"] = str(base_dir)
    runtime_section["config_dir"] = str(base_dir / "sentientos_data" / "config")
    cathedral_section = config.setdefault("cathedral", {})  # type: ignore[assignment]
    cathedral_section["ledger_path"] = str(base_dir / "cathedral" / "ledger.jsonl")
    cathedral_section["rollback_dir"] = str(base_dir / "cathedral" / "rollback")
    config_dir = Path(runtime_section["config_dir"])
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "runtime.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config


def _make_amendment(identifier: str, changes: dict[str, object]) -> Amendment:
    return Amendment(
        id=identifier,
        created_at=datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc),
        proposer="test",
        summary="Test amendment",
        changes=changes,
        reason="Routine configuration update.",
    )


def test_applicator_updates_runtime_config(runtime_config: dict[str, object]) -> None:
    applicator = AmendmentApplicator(runtime_config)
    amendment = _make_amendment(
        "cfg-1",
        {
            "config": {"runtime": {"watchdog_interval": 3}},
            "persona": {"tick_interval_seconds": 45},
            "world": {"enabled": False},
        },
    )
    result = applicator.apply(amendment)

    assert result.status == "applied"
    assert result.applied["config"]["runtime"]["watchdog_interval"]["value"] == 3
    assert result.applied["persona"]["tick_interval_seconds"]["value"] == 45
    config_path = Path(runtime_config["runtime"]["config_dir"]) / "runtime.json"  # type: ignore[index]
    stored = json.loads(config_path.read_text(encoding="utf-8"))
    assert stored["runtime"]["watchdog_interval"] == 3
    assert stored["persona"]["tick_interval_seconds"] == 45


def test_applicator_partial_when_skipping_entries(runtime_config: dict[str, object]) -> None:
    applicator = AmendmentApplicator(runtime_config)
    amendment = _make_amendment(
        "cfg-2",
        {
            "registry": {"demos": {"add": ["demo_new"], "remove": ["missing"]}},
        },
    )
    result = applicator.apply(amendment)

    assert result.status == "partial"
    assert "demo_new" in result.applied["registry"]["demos"]["added"]
    assert "registry.demos.missing" in result.skipped


def test_applicator_rejects_forbidden_domain(runtime_config: dict[str, object]) -> None:
    applicator = AmendmentApplicator(runtime_config)
    amendment = _make_amendment("cfg-3", {"source_code": {"update": "print('hi')"}})
    result = applicator.apply(amendment)

    assert result.status == "error"
    assert "source_code" in result.errors
    ledger_path = Path(runtime_config["cathedral"]["ledger_path"])  # type: ignore[index]
    assert not ledger_path.exists()


@pytest.mark.no_legacy_skip
def test_path_values_require_component_aware_base_ancestry(
    runtime_config: dict[str, object],
) -> None:
    applicator = AmendmentApplicator(runtime_config)
    base_dir = Path(runtime_config["runtime"]["root"])  # type: ignore[index]

    assert applicator._is_safe_value(str(base_dir / "config" / "nested.json"))
    assert not applicator._is_safe_value(str(base_dir) + "-backup/config.json")
    assert not applicator._is_safe_value(str(base_dir / ".." / "outside.json"))


@pytest.mark.no_legacy_skip
def test_sibling_prefix_path_amendment_is_rejected_without_persistence(
    runtime_config: dict[str, object],
) -> None:
    applicator = AmendmentApplicator(runtime_config)
    base_dir = Path(runtime_config["runtime"]["root"])  # type: ignore[index]
    sibling_path = str(base_dir) + "-backup/payload.json"
    amendment = _make_amendment(
        "cfg-sibling-prefix-path",
        {"config": {"runtime": {"watchdog_interval": sibling_path}}},
    )

    result = applicator.apply(amendment)

    assert result.status == "error"
    assert result.errors["config.runtime.watchdog_interval"] == "Unsafe value rejected"
    assert not Path(sibling_path).exists()
    assert not Path(runtime_config["cathedral"]["ledger_path"]).exists()  # type: ignore[index]


@pytest.mark.no_legacy_skip
def test_external_storage_overrides_fail_before_directory_creation(tmp_path: Path) -> None:
    for field in ("config_dir", "ledger_path", "rollback_dir"):
        base_dir = tmp_path / f"SentientOS-{field}"
        external_dir = tmp_path / f"external-{field}"
        config = bootstrap.build_default_config(base_dir)
        runtime = config["runtime"]  # type: ignore[index]
        runtime["root"] = str(base_dir)
        cathedral = config.setdefault("cathedral", {})  # type: ignore[assignment]
        if field == "config_dir":
            runtime[field] = str(external_dir)
        else:
            cathedral[field] = str(external_dir / ("ledger.jsonl" if field == "ledger_path" else "rollback"))

        with pytest.raises(ValueError, match="cathedral_storage_path_outside_base"):
            AmendmentApplicator(config)

        assert not base_dir.exists()
        assert not external_dir.exists()


@pytest.mark.no_legacy_skip
def test_symlinked_storage_override_outside_root_fails_before_directory_creation(
    tmp_path: Path,
) -> None:
    base_dir = tmp_path / "SentientOS"
    external_dir = tmp_path / "external"
    base_dir.mkdir()
    external_dir.mkdir()
    redirect = base_dir / "redirect"
    try:
        redirect.symlink_to(external_dir, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"directory symlinks are unavailable: {exc}")
    config = bootstrap.build_default_config(base_dir)
    config["runtime"]["root"] = str(base_dir)  # type: ignore[index]
    config.setdefault("cathedral", {})["ledger_path"] = str(redirect / "ledger.jsonl")  # type: ignore[index]

    with pytest.raises(ValueError, match="cathedral_storage_path_outside_base"):
        AmendmentApplicator(config)

    assert not (base_dir / "sentientos_data").exists()
    assert not (base_dir / "cathedral").exists()
    assert not (external_dir / "ledger.jsonl").exists()


@pytest.mark.no_legacy_skip
def test_in_root_storage_overrides_remain_supported(tmp_path: Path) -> None:
    base_dir = tmp_path / "SentientOS"
    config = bootstrap.build_default_config(base_dir)
    config["runtime"]["root"] = str(base_dir)  # type: ignore[index]
    config["runtime"]["config_dir"] = "sentientos_data/custom-config"  # type: ignore[index]
    config.setdefault("cathedral", {})["ledger_path"] = "cathedral/custom-ledger.jsonl"  # type: ignore[index]
    config["cathedral"]["rollback_dir"] = "cathedral/custom-rollback"  # type: ignore[index]

    applicator = AmendmentApplicator(config)
    result = applicator.apply(
        _make_amendment("cfg-in-root-storage", {"persona": {"tick_interval_seconds": 42}})
    )

    assert result.status == "applied"
    assert applicator._config_path == base_dir / "sentientos_data" / "custom-config" / "runtime.json"
    assert applicator.ledger_path == base_dir / "cathedral" / "custom-ledger.jsonl"
    assert applicator.rollback_dir == base_dir / "cathedral" / "custom-rollback"
    assert applicator._config_path.is_file()
    assert applicator.ledger_path.is_file()
    assert (applicator.rollback_dir / "cfg-in-root-storage.json").is_file()
