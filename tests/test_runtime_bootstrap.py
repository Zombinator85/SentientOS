import json
import os
from pathlib import Path

import pytest

from sentientos.runtime import bootstrap


def test_ensure_runtime_dirs_creates_expected_layout(tmp_path: Path) -> None:
    base_dir = tmp_path / "SentientOS"
    paths = bootstrap.ensure_runtime_dirs(base_dir)

    assert paths["base"] == base_dir
    assert paths["logs"] == base_dir / "logs"
    assert paths["data"] == base_dir / "sentientos_data"
    assert paths["models"] == base_dir / "sentientos_data" / "models"
    assert paths["config"] == base_dir / "sentientos_data" / "config"

    for directory in paths.values():
        assert directory.exists()


def test_ensure_default_config_creates_file_once(tmp_path: Path) -> None:
    paths = bootstrap.ensure_runtime_dirs(tmp_path / "SentientOS")
    config_path = bootstrap.ensure_default_config(paths["config"])
    assert config_path.exists()

    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert {"runtime", "persona", "dashboard"}.issubset(data.keys())

    original_content = config_path.read_text(encoding="utf-8")
    second_path = bootstrap.ensure_default_config(paths["config"])
    assert second_path == config_path
    assert config_path.read_text(encoding="utf-8") == original_content


def test_validate_model_paths_detects_missing_and_existing(tmp_path: Path) -> None:
    paths = bootstrap.ensure_runtime_dirs(tmp_path / "SentientOS")
    config = bootstrap.build_default_config(paths["base"])

    warnings = bootstrap.validate_model_paths(config, paths["base"])
    assert any("Mixtral" in message for message in warnings)

    model_path = Path(config["runtime"]["model_path"])
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.touch()

    llama_path = Path(config["runtime"]["llama_server_path"])
    llama_path.parent.mkdir(parents=True, exist_ok=True)
    llama_path.touch()

    warnings = bootstrap.validate_model_paths(config, paths["base"])
    assert warnings == []


def test_get_base_dir_honors_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENTIENTOS_BASE_DIR", str(tmp_path))
    try:
        assert bootstrap.get_base_dir() == tmp_path
    finally:
        monkeypatch.delenv("SENTIENTOS_BASE_DIR", raising=False)

    base_dir = bootstrap.get_base_dir()
    assert isinstance(base_dir, Path)
    data_dir = base_dir / "sentientos_data"
    assert isinstance(data_dir, Path)
