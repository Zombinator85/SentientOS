from pathlib import Path


def test_lock_files_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    for name in ("lock-bin.txt", "lock-src.txt"):
        path = root / name
        assert path.exists(), f"missing {name}"
        lines = path.read_text().splitlines()
        assert lines[0].startswith('#')
        assert any("--hash=" in l for l in lines)

