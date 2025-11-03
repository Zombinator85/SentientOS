import subprocess
from pathlib import Path


def _run_scan(path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "scripts/scan_secrets.sh", str(path)],
        capture_output=True,
        text=True,
    )


def test_scan_secrets_detects_token(tmp_path: Path) -> None:
    suspect = tmp_path / "token.txt"
    suspect.write_text("Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456", encoding="utf-8")
    result = _run_scan(suspect)
    assert result.returncode != 0
    assert "Potential secret" in result.stderr


def test_scan_secrets_passes_clean_file(tmp_path: Path) -> None:
    clean = tmp_path / "clean.txt"
    clean.write_text("hello world", encoding="utf-8")
    result = _run_scan(clean)
    assert result.returncode == 0
