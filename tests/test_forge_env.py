from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from sentientos import forge_env
from sentientos.forge_env_cache import ForgeEnvCacheEntry, ForgeEnvKey, prune_cache, resolve_cached_env


def test_bootstrap_env_reuses_cache_across_sessions(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path
    (repo_root / "pyproject.toml").write_text(
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
            (path / "bin" / "pip").write_text("", encoding="utf-8")

    def fake_run(argv, cwd, capture_output, text, check):
        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr("sentientos.forge_env_cache.venv.EnvBuilder", FakeBuilder)
    monkeypatch.setattr("sentientos.forge_env_cache.subprocess.run", fake_run)

    first = forge_env.bootstrap_env(repo_root)
    second = resolve_cached_env(repo_root, "test")

    assert first.created is True
    assert second.created is False
    assert first.venv_path == second.venv_path


def test_bootstrap_env_creates_marker_and_meta(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.1.0'\n", encoding="utf-8")

    class FakeBuilder:
        def __init__(self, **kwargs):
            pass

        def create(self, path: Path) -> None:
            (path / "bin").mkdir(parents=True, exist_ok=True)
            (path / "bin" / "python").write_text("", encoding="utf-8")
            (path / "bin" / "pip").write_text("", encoding="utf-8")

    def fake_run(argv, cwd, capture_output, text, check):
        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr("sentientos.forge_env_cache.venv.EnvBuilder", FakeBuilder)
    monkeypatch.setattr("sentientos.forge_env_cache.subprocess.run", fake_run)

    env = resolve_cached_env(tmp_path, "base")
    meta_path = Path(env.venv_path).parent / "meta.json"
    marker_path = Path(env.venv_path).parent / ".forge_env_ok"

    assert env.created is True
    assert marker_path.exists()
    assert meta_path.exists()
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    assert payload["marker_ok"] is True


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
            (path / "bin" / "pip").write_text("", encoding="utf-8")

    calls: list[list[str]] = []

    def fake_run(argv, cwd, capture_output, text, check):
        calls.append(argv)

        class R:
            returncode = 1 if ".[test]" in argv else 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr("sentientos.forge_env_cache.venv.EnvBuilder", FakeBuilder)
    monkeypatch.setattr("sentientos.forge_env_cache.subprocess.run", fake_run)

    env = forge_env.bootstrap_env(tmp_path)

    assert env.created is True
    assert "install[test]:rc=1" in env.install_summary
    assert "install_fallback:rc=0" in env.install_summary
    assert any(".[test]" in call for call in calls)
    assert any(call[-2:] == ["-e", "."] for call in calls)


def test_prune_cache_removes_old_entries(tmp_path: Path, monkeypatch) -> None:
    cache_root = tmp_path / ".forge" / "env_cache"
    old = cache_root / "old"
    keep = cache_root / "keep"
    old.mkdir(parents=True)
    keep.mkdir(parents=True)

    key = ForgeEnvKey("/py", "3.11", "abc", "base")
    old_entry = ForgeEnvCacheEntry(key=key, venv_path=str(old / "venv"), created_at="2020-01-01T00:00:00Z", last_used_at="2020-01-01T00:00:00Z", install_summary="ok", marker_ok=True)
    keep_entry = ForgeEnvCacheEntry(key=key, venv_path=str(keep / "venv"), created_at="2030-01-01T00:00:00Z", last_used_at="2030-01-01T00:00:00Z", install_summary="ok", marker_ok=True)
    (old / "meta.json").write_text(json.dumps(asdict(old_entry)), encoding="utf-8")
    (keep / "meta.json").write_text(json.dumps(asdict(keep_entry)), encoding="utf-8")

    removed_paths: list[str] = []

    def fake_rmtree(path: Path) -> None:
        removed_paths.append(path.name)

    monkeypatch.setattr("sentientos.forge_env_cache._safe_rmtree", fake_rmtree)

    removed = prune_cache(tmp_path, max_entries=5, max_age_days=14)

    assert "old" in removed
    assert "old" in removed_paths
    assert "keep" not in removed
