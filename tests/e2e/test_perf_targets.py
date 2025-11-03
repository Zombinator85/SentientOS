from pathlib import Path

from sentientos.perf_smoke import run_smoke


def test_perf_smoke_writes_summary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    result = run_smoke("1s", "low")
    summary = tmp_path / "glow" / "perf" / "latest" / "summary.json"
    assert summary.exists()
    payload = summary.read_text(encoding="utf-8")
    assert "critic" in result
    assert "p50" in payload
