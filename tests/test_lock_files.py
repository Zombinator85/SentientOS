from pathlib import Path


def test_lock_files_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    for name in ("lock-bin.txt", "lock-src.txt"):
        path = root / name
        assert path.exists(), f"missing {name}"
        lines = [l for l in path.read_text().splitlines() if l and not l.startswith('#')]
        assert len(lines) >= 5
        assert all("--hash=sha256:" in l for l in lines)

