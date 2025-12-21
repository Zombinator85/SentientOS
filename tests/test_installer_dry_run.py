import hashlib
import json
from pathlib import Path

import pytest

from installer.dry_run import HardwareProfile, InstallerError, dry_run_install


pytestmark = pytest.mark.no_legacy_skip


def _build_manifest(tmp_path: Path, payload: bytes = b"model", *, size_bytes: int | None = None) -> Path:
    artifact_path = tmp_path / "artifact.gguf"
    artifact_path.write_bytes(payload)
    manifest = {
        "manifest_version": "v1",
        "models": [
            {
                "id": "model",
                "artifact": {
                    "escrow_path": str(artifact_path),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size_bytes": size_bytes if size_bytes is not None else len(payload),
                    "urls": [str(artifact_path)],
                },
                "requirements": {"ram_gb_min": 8, "avx2": True, "avx512": False},
            }
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def _hardware_meeting_minimum() -> HardwareProfile:
    return HardwareProfile(ram_gb=8, avx=True, avx2=True, avx512=False)


def test_dry_run_network_unavailable(tmp_path: Path) -> None:
    manifest_path = _build_manifest(tmp_path)
    install_dir = tmp_path / "install"
    with pytest.raises(InstallerError, match="Network unavailable"):
        dry_run_install(
            manifest_path,
            install_dir,
            hardware=_hardware_meeting_minimum(),
            network_available=False,
        )


def test_dry_run_partial_download(tmp_path: Path) -> None:
    manifest_path = _build_manifest(tmp_path, payload=b"abcdef")
    install_dir = tmp_path / "install"

    def fetch_partial(entry: dict) -> bytes:
        escrow_path = Path(entry["artifact"]["escrow_path"])
        data = escrow_path.read_bytes()
        return data[: max(1, len(data) // 2)]

    with pytest.raises(InstallerError, match="Partial download"):
        dry_run_install(
            manifest_path,
            install_dir,
            hardware=_hardware_meeting_minimum(),
            fetcher=fetch_partial,
        )


def test_dry_run_checksum_injected(tmp_path: Path) -> None:
    manifest_path = _build_manifest(tmp_path)
    install_dir = tmp_path / "install"

    def fetch_corrupt(entry: dict) -> bytes:
        return b"corrupted-payload"

    with pytest.raises(InstallerError, match="Checksum mismatch"):
        dry_run_install(
            manifest_path,
            install_dir,
            hardware=_hardware_meeting_minimum(),
            fetcher=fetch_corrupt,
        )


def test_dry_run_insufficient_disk(tmp_path: Path) -> None:
    manifest_path = _build_manifest(tmp_path, payload=b"abc", size_bytes=10)
    install_dir = tmp_path / "install"
    with pytest.raises(InstallerError, match="Insufficient disk"):
        dry_run_install(
            manifest_path,
            install_dir,
            hardware=_hardware_meeting_minimum(),
            available_bytes=1,
        )


def test_dry_run_reuses_existing_artifact_when_offline(tmp_path: Path) -> None:
    manifest_path = _build_manifest(tmp_path, payload=b"payload")
    install_dir = tmp_path / "install"
    destination = install_dir / "artifact.gguf"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"payload")

    result = dry_run_install(
        manifest_path,
        install_dir,
        hardware=_hardware_meeting_minimum(),
        network_available=False,
        available_bytes=0,
    )

    assert result == destination
    assert destination.read_bytes() == b"payload"


def test_dry_run_rejects_conflicting_existing_artifact(tmp_path: Path) -> None:
    manifest_path = _build_manifest(tmp_path, payload=b"payload")
    install_dir = tmp_path / "install"
    destination = install_dir / "artifact.gguf"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"payload-corrupt")

    with pytest.raises(InstallerError, match="Existing artifact checksum mismatch"):
        dry_run_install(
            manifest_path,
            install_dir,
            hardware=_hardware_meeting_minimum(),
        )


def test_dry_run_hardware_exact_threshold(tmp_path: Path) -> None:
    manifest_path = _build_manifest(tmp_path, payload=b"payload")
    install_dir = tmp_path / "install"
    destination = dry_run_install(
        manifest_path,
        install_dir,
        hardware=_hardware_meeting_minimum(),
        available_bytes=len(b"payload"),
    )
    assert destination.exists()
    assert destination.read_bytes() == b"payload"


def test_dry_run_rejects_hardware_below_minimum(tmp_path: Path) -> None:
    manifest_path = _build_manifest(tmp_path)
    install_dir = tmp_path / "install"
    with pytest.raises(InstallerError, match="Insufficient RAM"):
        dry_run_install(
            manifest_path,
            install_dir,
            hardware=HardwareProfile(ram_gb=4, avx=True, avx2=False, avx512=False),
        )
