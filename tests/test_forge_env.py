from __future__ import annotations

from pathlib import Path

from sentientos import forge_env


def test_bootstrap_env_reuses_marker(tmp_path: Path) -> None:
    venv_path = tmp_path / ".forge" / "venv"
    bin_path = venv_path / "bin"
    bin_path.mkdir(parents=True)
    (bin_path / "python").write_text("", encoding="utf-8")
    (venv_path / ".forge_env_ok").write_text('{"summary": "ok"}', encoding="utf-8")

    env = forge_env.bootstrap_env(tmp_path)

    assert env.created is False
    assert env.python.endswith("bin/python")
    assert env.install_summary == "ok"


def test_bootstrap_env_creates_and_marks(tmp_path: Path, monkeypatch) -> None:
    created = {"value": False}

    class FakeBuilder:
        def __init__(self, **kwargs):
            pass

        def create(self, path: Path) -> None:
            created["value"] = True
            (path / "bin").mkdir(parents=True, exist_ok=True)
            (path / "bin" / "python").write_text("", encoding="utf-8")

    def fake_run(argv, cwd, capture_output, text, check):
        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(forge_env.venv, "EnvBuilder", FakeBuilder)
    monkeypatch.setattr(forge_env.subprocess, "run", fake_run)

    env = forge_env.bootstrap_env(tmp_path)

    assert created["value"] is True
    assert env.created is True
    assert (Path(env.venv_path) / ".forge_env_ok").exists()
