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
