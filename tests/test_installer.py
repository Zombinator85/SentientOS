from __future__ import annotations

import hashlib
import json
from importlib import reload
from pathlib import Path

import pytest


def _write_manifest(tmp_path: Path, payload: bytes = b"payload") -> tuple[Path, Path]:
    escrow_path = tmp_path / "escrow" / "artifact.bin"
    escrow_path.parent.mkdir(parents=True, exist_ok=True)
    escrow_path.write_bytes(payload)
    manifest = {
        "manifest_version": "v1",
        "models": [
            {
                "artifact": {
                    "escrow_path": str(escrow_path.relative_to(tmp_path)),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size_bytes": len(payload),
                    "urls": [],
                },
                "id": "test-artifact",
                "requirements": {"ram_gb_min": 0, "avx2": False, "avx512": False},
            }
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path, escrow_path


def test_installer_default_offline_no_pip(tmp_path, monkeypatch):
    manifest_path, _ = _write_manifest(tmp_path)
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path / "logs"))
    import installer.setup_installer as si

    reload(si)
    monkeypatch.setattr(si, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(si, "SAMPLES_DIR", tmp_path / "samples")
    monkeypatch.setattr(si, "ENV_EXAMPLE", tmp_path / ".env.example")
    monkeypatch.setattr(si, "ENV_FILE", tmp_path / ".env")
    (tmp_path / "samples").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(si, "DEFAULT_LOCK_FILE", tmp_path / "requirements-lock.txt")
    monkeypatch.setattr(si, "DEFAULT_MANIFEST", manifest_path)
    monkeypatch.setattr(
        si,
        "install_dependencies",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("pip should be opt-in")),
    )
    monkeypatch.setattr(si, "smoke_test", lambda: None)
    monkeypatch.setattr(si, "check_microphone", lambda: None)

    si.main(["--manifest", str(manifest_path), "--escrow-root", str(tmp_path)])


def test_manifest_hash_mismatch_blocks(tmp_path, monkeypatch):
    manifest_path, escrow_path = _write_manifest(tmp_path, payload=b"first")
    bad_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    bad_manifest["models"][0]["artifact"]["sha256"] = hashlib.sha256(b"second").hexdigest()
    manifest_path.write_text(json.dumps(bad_manifest), encoding="utf-8")

    import installer.setup_installer as si

    reload(si)
    with pytest.raises(RuntimeError):
        si.verify_manifest_artifacts(manifest_path, escrow_root=tmp_path)
