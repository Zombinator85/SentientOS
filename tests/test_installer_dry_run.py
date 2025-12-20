import json
from pathlib import Path

import pytest

from installer.dry_run import HardwareProfile, InstallerError, dry_run_install


MANIFEST_PATH = Path("manifests/manifest-v1.json")


def _hardware_meeting_minimum() -> HardwareProfile:
    return HardwareProfile(ram_gb=8, avx=True, avx2=True, avx512=False)


def _first_artifact_path() -> Path:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return Path(data["models"][0]["artifact"]["escrow_path"])


def test_dry_run_network_unavailable(tmp_path: Path) -> None:
    with pytest.raises(InstallerError, match="Network unavailable"):
        dry_run_install(
            MANIFEST_PATH,
            tmp_path,
            hardware=_hardware_meeting_minimum(),
            network_available=False,
        )


def test_dry_run_partial_download(tmp_path: Path) -> None:
    def fetch_partial(entry: dict) -> bytes:
        escrow_path = Path(entry["artifact"]["escrow_path"])
        data = escrow_path.read_bytes()
        return data[: max(1, len(data) // 2)]

    with pytest.raises(InstallerError, match="Partial download"):
        dry_run_install(
            MANIFEST_PATH,
            tmp_path,
            hardware=_hardware_meeting_minimum(),
            fetcher=fetch_partial,
        )


def test_dry_run_checksum_injected(tmp_path: Path) -> None:
    def fetch_corrupt(entry: dict) -> bytes:
        return b"corrupted-payload"

    with pytest.raises(InstallerError, match="Checksum mismatch"):
        dry_run_install(
            MANIFEST_PATH,
            tmp_path,
            hardware=_hardware_meeting_minimum(),
            fetcher=fetch_corrupt,
        )


def test_dry_run_insufficient_disk(tmp_path: Path) -> None:
    with pytest.raises(InstallerError, match="Insufficient disk"):
        dry_run_install(
            MANIFEST_PATH,
            tmp_path,
            hardware=_hardware_meeting_minimum(),
            available_bytes=1,
        )


def test_dry_run_hardware_exact_threshold(tmp_path: Path) -> None:
    escrow_path = _first_artifact_path()
    destination = dry_run_install(
        MANIFEST_PATH,
        tmp_path,
        hardware=_hardware_meeting_minimum(),
        available_bytes=1024,
    )
    assert destination.exists()
    assert destination.read_bytes() == escrow_path.read_bytes()


def test_dry_run_rejects_hardware_below_minimum(tmp_path: Path) -> None:
    with pytest.raises(InstallerError, match="Insufficient RAM"):
        dry_run_install(
            MANIFEST_PATH,
            tmp_path,
            hardware=HardwareProfile(ram_gb=4, avx=True, avx2=False, avx512=False),
        )
