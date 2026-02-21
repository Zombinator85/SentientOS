from __future__ import annotations

import json
from pathlib import Path

from sentientos.cathedral_forge import CathedralForge


def test_diagnostics_only_produces_sweep_artifacts(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_MODE_FORCE", "recovery")
    monkeypatch.setenv("SENTIENTOS_FORGE_DIAGNOSTICS_ONLY", "1")
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text('{"baseline_integrity_ok": true, "runtime_integrity_ok": true, "baseline_unexpected_change_detected": false}\n', encoding="utf-8")

    report = CathedralForge(repo_root=tmp_path).run("forge_smoke_noop")
    assert report.outcome == "diagnostics_only"

    sweeps = sorted((tmp_path / "glow/forge/sweeps").glob("sweep_*.json"))
    assert sweeps
    payload = json.loads(sweeps[-1].read_text(encoding="utf-8"))
    assert payload["mode"] == "recovery"
    assert (tmp_path / "pulse/sweeps.jsonl").exists()
