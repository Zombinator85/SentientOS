from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts import verify_audits
from sentientos.audit_sink import resolve_audit_paths, safe_write_event


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def test_runtime_events_do_not_flag_baseline_drift(tmp_path: Path, monkeypatch) -> None:
    baseline = tmp_path / "logs" / "privileged_audit.jsonl"
    runtime_dir = tmp_path / "pulse" / "audit"
    baseline.parent.mkdir(parents=True)
    baseline.write_text("", encoding="utf-8")

    monkeypatch.setenv("SENTIENTOS_AUDIT_BASELINE_PATH", str(baseline))
    monkeypatch.setenv("SENTIENTOS_AUDIT_RUNTIME_DIR", str(runtime_dir))

    cfg = resolve_audit_paths(Path.cwd())
    safe_write_event(
        cfg,
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "prev_hash": "0" * 64,
            "rolling_hash": "x",
            "data": {"tool": "test"},
        },
    )

    baseline_before = _hash(baseline)
    status = verify_audits._strict_privileged_status(cfg)
    assert status["baseline_status"] == "ok"
    assert status["runtime_status"] in {"ok", "broken"}
    assert _hash(baseline) == baseline_before


def test_show_paths_and_runtime_override(capsys, tmp_path: Path) -> None:
    runtime_dir = tmp_path / "audit"
    rc = verify_audits.main(["--strict", "--show-paths", "--runtime-dir", str(runtime_dir)])
    out = capsys.readouterr().out
    assert rc in {0, 1}
    lines = [line for line in out.splitlines() if line.startswith("{")]
    payloads = [json.loads(line) for line in lines]
    assert any("runtime_path" in item for item in payloads)
