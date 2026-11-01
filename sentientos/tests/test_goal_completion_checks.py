from __future__ import annotations

from pathlib import Path

from sentientos.artifact_catalog import append_catalog_entry
from sentientos.goal_completion import CompletionContext, eval_check


def _seed(tmp_path: Path, rel: str, payload: str) -> str:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload + "\n", encoding="utf-8")
    return rel


def test_checks_done_and_unknown(tmp_path: Path) -> None:
    _seed(tmp_path, "glow/forge/work_runs/run.json", '{"schema_version":3,"run_id":"r1","status":"ok","evidence_digest":"' + "a" * 64 + '"}')
    append_catalog_entry(tmp_path, kind="work_run", artifact_id="r1", relative_path="glow/forge/work_runs/run.json", schema_name="", schema_version=3, links={"goal_ids": ["g1"], "work_run_id": "r1"}, summary={"status": "ok"})
    ctx = CompletionContext(tmp_path, "g1", "normal", 0, "balanced", False, {})
    unbound = eval_check("check_forge_last_run_ok", ctx)
    assert unbound.done is False
    assert "run_evidence_binding_missing" in unbound.reason_stack
    claimed_ctx = CompletionContext(tmp_path, "g1", "normal", 0, "balanced", False, {}, "r1", "a" * 64)
    assert eval_check("check_forge_last_run_ok", claimed_ctx).done is False
    assert eval_check("check_witnesses_ok", ctx).status == "unknown"


def test_missing_artifacts_stable_reasons(tmp_path: Path) -> None:
    ctx = CompletionContext(tmp_path, "g1", "normal", 0, "balanced", False, {})
    result = eval_check("check_federation_ok", ctx)
    assert result.reason_stack == ("artifact_missing",)


def test_non_run_completion_proof_binds_exact_artifact_bytes(tmp_path: Path) -> None:
    relative_path = _seed(
        tmp_path, "glow/federation/snapshots/snapshot.json",
        '{"schema_version":1,"status":"ok"}',
    )
    append_catalog_entry(
        tmp_path, kind="federation_snapshot", artifact_id="snapshot-1",
        relative_path=relative_path, schema_name="", schema_version=1,
        summary={"status": "ok"},
    )
    ctx = CompletionContext(tmp_path, "g1", "normal", 0, "balanced", False, {})

    first = eval_check("check_federation_ok", ctx)
    assert first.done is True
    assert first.evidence_digest is not None

    (tmp_path / relative_path).write_text(
        '{"schema_version":1,"status":"ok","generation":2}\n',
        encoding="utf-8",
    )
    second = eval_check("check_federation_ok", ctx)
    assert second.done is True
    assert second.evidence_digest != first.evidence_digest


def test_done_check_without_readable_evidence_fails_closed(tmp_path: Path) -> None:
    append_catalog_entry(
        tmp_path, kind="federation_snapshot", artifact_id="missing-snapshot",
        relative_path="glow/federation/snapshots/missing.json", schema_name="",
        schema_version=1, summary={"status": "ok"},
    )
    result = eval_check(
        "check_federation_ok",
        CompletionContext(tmp_path, "g1", "normal", 0, "balanced", False, {}),
    )
    assert result.done is False
    assert result.status == "blocked"
    assert "completion_evidence_binding_missing" in result.reason_stack


def test_federation_check_treats_malformed_summary_as_missing_metadata(
    tmp_path: Path, monkeypatch,
) -> None:
    row: dict[str, object] = {"summary": ["not", "a", "mapping"]}
    monkeypatch.setattr(
        CompletionContext,
        "latest",
        lambda _self, kind: row if kind == "federation_snapshot" else None,
    )
    monkeypatch.setattr(
        CompletionContext,
        "load_normalized",
        lambda _self, _entry, *, fallback_schema=None: (None, ()),
    )
    ctx = CompletionContext(tmp_path, "g1", "normal", 0, "balanced", False, {})

    result = eval_check("check_federation_ok", ctx)

    assert result.done is False
    assert result.status == "blocked"
    assert "verify_failed" in result.reason_stack


def test_mypy_forge_check_treats_malformed_run_summary_as_missing_metadata(
    tmp_path: Path, monkeypatch,
) -> None:
    verify_row: dict[str, object] = {"summary": {}}
    run_row: dict[str, object] = {"summary": ["not", "a", "mapping"]}
    monkeypatch.setattr(
        CompletionContext,
        "latest",
        lambda _self, kind: verify_row if kind == "verify_result" else None,
    )
    monkeypatch.setattr(
        CompletionContext,
        "latest_for_goal",
        lambda _self, kind: run_row if kind == "work_run" else None,
    )
    monkeypatch.setattr(
        "sentientos.goal_completion.artifact_catalog.load_catalog_artifact",
        lambda _root, _entry: {},
    )
    ctx = CompletionContext(tmp_path, "g1", "normal", 0, "balanced", False, {})

    result = eval_check("check_mypy_forge_ok", ctx)

    assert result.done is False
    assert result.status == "unknown"
    assert "verify_failed" in result.reason_stack
