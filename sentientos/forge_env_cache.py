"""Shared Forge environment cache for CathedralForge sessions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import venv


@dataclass(slots=True)
class ForgeEnvKey:
    python_executable: str
    python_version: str
    project_fingerprint: str
    extras_tag: str


@dataclass(slots=True)
class ForgeEnvCacheEntry:
    key: ForgeEnvKey
    venv_path: str
    created_at: str
    last_used_at: str
    install_summary: str
    marker_ok: bool


def resolve_cached_env(repo_root: Path, want_extras: str | None) -> "ForgeEnv":
    from sentientos.forge_env import ForgeEnv

    key = _build_key(repo_root, want_extras)
    cache_hash = _key_hash(key)
    entry_dir = _cache_entry_dir(repo_root, cache_hash)
    venv_path = entry_dir / "venv"
    marker = entry_dir / ".forge_env_ok"
    meta_path = entry_dir / "meta.json"
    python_path = _venv_python(venv_path)
    pip_path = _venv_pip(venv_path)

    now = _iso_now()
    entry_dir.mkdir(parents=True, exist_ok=True)
    existing = _read_meta(meta_path)

    if marker.exists() and python_path.exists() and existing is not None:
        existing.last_used_at = now
        _write_meta(meta_path, existing)
        return ForgeEnv(
            python=str(python_path),
            pip=str(pip_path),
            venv_path=str(venv_path),
            created=False,
            install_summary=existing.install_summary or "reused",
            cache_key=cache_hash,
        )

    builder = venv.EnvBuilder(with_pip=True, clear=False)
    builder.create(venv_path)

    summary: list[str] = []
    summary.append(
        _run_best_effort(
            [str(python_path), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
            repo_root,
            "upgrade",
        )
    )
    install_summary, _ = _install_repo(python_path, repo_root, key.extras_tag)
    summary.append(install_summary)
    combined = " | ".join(summary)

    marker.write_text(json.dumps({"summary": combined}, sort_keys=True), encoding="utf-8")
    created_at = existing.created_at if existing is not None else now
    entry = ForgeEnvCacheEntry(
        key=key,
        venv_path=str(venv_path),
        created_at=created_at,
        last_used_at=now,
        install_summary=combined,
        marker_ok=True,
    )
    _write_meta(meta_path, entry)
    return ForgeEnv(
        python=str(python_path),
        pip=str(pip_path),
        venv_path=str(venv_path),
        created=True,
        install_summary=combined,
        cache_key=cache_hash,
    )


def prune_cache(repo_root: Path, max_entries: int = 5, max_age_days: int = 14) -> list[str]:
    cache_root = _cache_root(repo_root)
    if not cache_root.exists():
        return []
    removed: list[str] = []
    entries: list[tuple[Path, ForgeEnvCacheEntry | None]] = []
    for child in sorted(cache_root.iterdir()):
        if not child.is_dir():
            continue
        meta = _read_meta(child / "meta.json")
        entries.append((child, meta))

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    survivors: list[tuple[Path, ForgeEnvCacheEntry | None]] = []
    for path, meta in entries:
        when = _parse_iso(meta.last_used_at) if meta is not None else None
        if when is not None and when < cutoff:
            _safe_rmtree(path)
            removed.append(path.name)
            continue
        survivors.append((path, meta))

    if len(survivors) <= max_entries:
        return removed

    survivors_sorted = sorted(
        survivors,
        key=lambda item: _parse_iso(item[1].last_used_at) if item[1] is not None else datetime.min.replace(tzinfo=timezone.utc),
    )
    for path, _meta in survivors_sorted[: max(0, len(survivors_sorted) - max_entries)]:
        _safe_rmtree(path)
        removed.append(path.name)
    return removed


def list_cache_entries(repo_root: Path) -> list[ForgeEnvCacheEntry]:
    root = _cache_root(repo_root)
    if not root.exists():
        return []
    entries: list[ForgeEnvCacheEntry] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        meta = _read_meta(child / "meta.json")
        if meta is not None:
            entries.append(meta)
    return entries


def _cache_root(repo_root: Path) -> Path:
    return repo_root / ".forge" / "env_cache"


def _cache_entry_dir(repo_root: Path, cache_hash: str) -> Path:
    return _cache_root(repo_root) / cache_hash


def _build_key(repo_root: Path, want_extras: str | None) -> ForgeEnvKey:
    py_major_minor = f"{sys.version_info.major}.{sys.version_info.minor}"
    return ForgeEnvKey(
        python_executable=str(Path(sys.executable).resolve()),
        python_version=py_major_minor,
        project_fingerprint=_project_fingerprint(repo_root),
        extras_tag=want_extras or "base",
    )


def _project_fingerprint(repo_root: Path) -> str:
    digest = hashlib.sha256()
    candidates = ["pyproject.toml", "requirements.txt", "requirements-dev.txt", "requirements-test.txt"]
    found = False
    for name in candidates:
        path = repo_root / name
        if not path.exists():
            continue
        found = True
        digest.update(name.encode("utf-8"))
        digest.update(path.read_bytes())
    if not found:
        digest.update(b"no-dependency-manifest")
    return digest.hexdigest()


def _key_hash(key: ForgeEnvKey) -> str:
    payload = json.dumps(asdict(key), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _run_best_effort(argv: list[str], cwd: Path, label: str) -> str:
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
    return f"{label}:rc={result.returncode}"


def _install_repo(python_path: Path, repo_root: Path, extras_tag: str) -> tuple[str, bool]:
    if extras_tag == "test":
        test_summary = _run_best_effort([str(python_path), "-m", "pip", "install", "-e", ".[test]"], repo_root, "install[test]")
        if test_summary.endswith("rc=0"):
            return test_summary, True
        fallback_summary = _run_best_effort([str(python_path), "-m", "pip", "install", "-e", "."], repo_root, "install_fallback")
        return f"{test_summary} | {fallback_summary}", fallback_summary.endswith("rc=0")
    base_summary = _run_best_effort([str(python_path), "-m", "pip", "install", "-e", "."], repo_root, "install")
    return base_summary, base_summary.endswith("rc=0")


def _venv_python(venv_path: Path) -> Path:
    if (venv_path / "Scripts" / "python.exe").exists():
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def _venv_pip(venv_path: Path) -> Path:
    if (venv_path / "Scripts" / "pip.exe").exists():
        return venv_path / "Scripts" / "pip.exe"
    return venv_path / "bin" / "pip"


def _read_meta(path: Path) -> ForgeEnvCacheEntry | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    key_payload = payload.get("key", {})
    if not isinstance(key_payload, dict):
        return None
    key = ForgeEnvKey(
        python_executable=str(key_payload.get("python_executable", "")),
        python_version=str(key_payload.get("python_version", "")),
        project_fingerprint=str(key_payload.get("project_fingerprint", "")),
        extras_tag=str(key_payload.get("extras_tag", "base")),
    )
    return ForgeEnvCacheEntry(
        key=key,
        venv_path=str(payload.get("venv_path", "")),
        created_at=str(payload.get("created_at", _iso_now())),
        last_used_at=str(payload.get("last_used_at", _iso_now())),
        install_summary=str(payload.get("install_summary", "")),
        marker_ok=bool(payload.get("marker_ok", False)),
    )


def _write_meta(path: Path, entry: ForgeEnvCacheEntry) -> None:
    path.write_text(json.dumps(asdict(entry), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _safe_rmtree(path: Path) -> None:
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", str(path)], capture_output=True, text=True, check=False)
        return
    subprocess.run(["rm", "-rf", str(path)], capture_output=True, text=True, check=False)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
