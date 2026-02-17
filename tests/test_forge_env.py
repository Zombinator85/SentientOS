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


def test_bootstrap_env_falls_back_when_test_extra_install_fails(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """[project]
name = "x"
version = "0.0.1"
[project.optional-dependencies]
test = ["pytest"]
""",
        encoding="utf-8",
    )

    class FakeBuilder:
        def __init__(self, **kwargs):
            pass

        def create(self, path: Path) -> None:
            (path / "bin").mkdir(parents=True, exist_ok=True)
            (path / "bin" / "python").write_text("", encoding="utf-8")

    calls: list[list[str]] = []

    def fake_run(argv, cwd, capture_output, text, check):
        calls.append(argv)

        class R:
            returncode = 1 if ".[test]" in argv else 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(forge_env.venv, "EnvBuilder", FakeBuilder)
    monkeypatch.setattr(forge_env.subprocess, "run", fake_run)

    env = forge_env.bootstrap_env(tmp_path)

    assert env.created is True
    assert "install[test]:rc=1" in env.install_summary
    assert "install_fallback:rc=0" in env.install_summary
    assert any(".[test]" in call for call in calls)
    assert any(call[-2:] == ["-e", "."] for call in calls)
