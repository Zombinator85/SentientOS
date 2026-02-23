from __future__ import annotations

from pathlib import Path

from sentientos.artifact_catalog import append_catalog_entry
from sentientos.goal_completion import CompletionContext, eval_check, get_check


def test_registry_lookup_and_unknown(tmp_path: Path) -> None:
    assert get_check("check_forge_last_run_ok") is not None
    ctx = CompletionContext(tmp_path, "g1", "normal", 0, "balanced", False, {})
    missing = eval_check("missing", ctx)
    assert missing.status == "error"
    assert missing.reason_stack == ("unknown_check",)


def test_schema_normalize_reason_stable(tmp_path: Path) -> None:
    path = tmp_path / "glow/forge/verify_results/v.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"schema_version": 0, "status":"ok"}\n', encoding="utf-8")
    append_catalog_entry(
        tmp_path,
        kind="verify_result",
        artifact_id="v1",
        relative_path=str(path.relative_to(tmp_path)),
        schema_name="receipt",
        schema_version=0,
        links={"goal_id": "g1"},
        summary={"status": "ok"},
    )
    ctx = CompletionContext(tmp_path, "g1", "normal", 0, "balanced", False, {})
    result = eval_check("check_integrity_baseline_ok", ctx)
    assert result.status in {"blocked", "unknown"}
    assert tuple(sorted(result.reason_stack)) == result.reason_stack
