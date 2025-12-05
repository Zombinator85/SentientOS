"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
import subprocess
import importlib
import sys
from pathlib import Path

import profile_manager as pm


def test_cli_reads_updated_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    importlib.reload(pm)
    monkeypatch.setattr(pm, "PROFILES_DIR", tmp_path / "profiles", raising=False)
    pm.PROFILES_DIR.mkdir()
    monkeypatch.setattr(pm, "CURRENT_FILE", pm.PROFILES_DIR / ".current", raising=False)
    monkeypatch.setattr(pm, "HOME_CURRENT", tmp_path / ".sentientos_profile", raising=False)

    pm.create_profile("default")
    env_path = pm.PROFILES_DIR / "default" / ".env"
    env_path.write_text("MODEL_SLUG=llama_cpp/mistral-7b-instruct-v0.2.Q4_K_M.gguf\n")
    pm.switch_profile("default")

    def run_cli() -> str:
        cp = subprocess.run(
            [sys.executable, "-c", "import os; print(os.getenv('MODEL_SLUG'))"],
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        return cp.stdout.strip()

    assert run_cli() == "llama_cpp/mistral-7b-instruct-v0.2.Q4_K_M.gguf"

    env_path.write_text("MODEL_SLUG=openai/gpt-4o\n")
    pm.switch_profile("default")

    assert run_cli() == "openai/gpt-4o"
