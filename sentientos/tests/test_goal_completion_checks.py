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
    _seed(tmp_path, "glow/forge/work_runs/run.json", '{"status":"ok"}')
    append_catalog_entry(tmp_path, kind="work_run", artifact_id="r1", relative_path="glow/forge/work_runs/run.json", schema_name="work_run", schema_version=1, links={"goal_id": "g1"}, summary={"status": "ok"})
    ctx = CompletionContext(tmp_path, "g1", "normal", 0, "balanced", False, {})
    assert eval_check("check_forge_last_run_ok", ctx).done is True
    assert eval_check("check_witnesses_ok", ctx).status == "unknown"


def test_missing_artifacts_stable_reasons(tmp_path: Path) -> None:
    ctx = CompletionContext(tmp_path, "g1", "normal", 0, "balanced", False, {})
    result = eval_check("check_federation_ok", ctx)
    assert result.reason_stack == ("artifact_missing",)
