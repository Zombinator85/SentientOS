"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations



import json
import verify_audits as va
import audit_immutability as ai
from pathlib import Path


def test_directory_verification(tmp_path: Path) -> None:
    d = tmp_path / "logs"
    d.mkdir()
    log1 = d / "a.jsonl"
    log2 = d / "b.jsonl"
    ai.append_entry(log1, {"x": 1})
    last = ai.read_entries(log1)[-1].rolling_hash
    # create an entry in log2 that links back to log1
    ts = "2025-01-01T00:00:00"
    digest = ai._hash_entry(ts, {"y": 2}, last)
    entry = {"timestamp": ts, "data": {"y": 2}, "prev_hash": last, "rolling_hash": digest}
    log2.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    results, percent, stats = va.verify_audits(directory=d)
    assert all(not e for e in results.values())
    assert percent == 100.0
    assert stats == {"fixed": 0, "quarantined": 0, "unrecoverable": 0}


def test_configured_verification_preserves_independent_stream_anchors(
    tmp_path: Path, monkeypatch
) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    first = logs / "a.jsonl"
    independent = logs / "b.jsonl"
    ai.append_entry(first, {"stream": "first"})
    anchor = "a" * 64
    timestamp = "2025-01-02T00:00:00"
    data = {"stream": "independent"}
    rolling_hash = ai._hash_entry(timestamp, data, anchor)
    independent.write_text(
        json.dumps(
            {
                "timestamp": timestamp,
                "data": data,
                "prev_hash": anchor,
                "rolling_hash": rolling_hash,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        va,
        "_load_config",
        lambda: {str(first): {}, str(independent): {}},
    )

    results, percent, _ = va.verify_audits(directory=None)
    assert all(not errors for errors in results.values())
    assert percent == 100.0

    directory_results, _, _ = va.verify_audits(directory=logs)
    assert any(directory_results[str(independent)])


def test_nightly_audit_workflows_keep_strict_configured_stream_checks() -> None:
    repository = Path(__file__).resolve().parents[1]
    for workflow in (
        repository / ".github/workflows/audit-nightly.yml",
        repository / ".github/workflows/nightly-self-check.yml",
    ):
        source = workflow.read_text(encoding="utf-8")
        assert "python -m scripts.verify_audits --strict --no-input" in source
        assert "python -m scripts.verify_audits logs/ --strict --no-input" not in source
        assert "sudo -n env" in source
