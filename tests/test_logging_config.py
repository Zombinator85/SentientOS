"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
from logging_config import get_log_dir, get_log_path, LOG_DIR_ENV


def test_get_log_dir_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(LOG_DIR_ENV, raising=False)
    path = get_log_dir()
    assert path.resolve() == (tmp_path / "logs").resolve()
    assert path.exists()


def test_get_log_dir_env_override(tmp_path, monkeypatch):
    custom = tmp_path / "mylogs"
    monkeypatch.setenv(LOG_DIR_ENV, str(custom))
    path = get_log_dir()
    assert path.resolve() == custom.resolve()
    assert path.exists()


def test_get_log_path_specific_env(tmp_path, monkeypatch):
    special = tmp_path / "special.log"
    monkeypatch.setenv("SPECIAL_LOG", str(special))
    result = get_log_path("fallback.log", "SPECIAL_LOG")
    assert result == special
