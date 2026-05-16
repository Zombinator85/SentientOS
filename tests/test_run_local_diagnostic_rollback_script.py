from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

from scripts import run_local_diagnostic_effect as effect_script
from scripts import run_local_diagnostic_rollback as rollback_script

pytestmark = pytest.mark.no_legacy_skip


def _run(args: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO(); stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            code = rollback_script.main(args)
        except SystemExit as exc:
            code = int(exc.code or 0)
    return code, stdout.getvalue(), stderr.getvalue()


def _effect(tmp_path: Path) -> tuple[Path, Path, Path]:
    code = effect_script.main(["--output-dir", str(tmp_path), "--summary", "--force"])
    assert code == 0
    return tmp_path / "effect_receipt.json", tmp_path / "rollback_plan.json", tmp_path / "sentientos_local_diagnostic_effect.json"


def test_requires_receipt_plan_and_scope() -> None:
    code, _out, err = _run([])
    assert code != 0
    assert "effect-receipt" in err


def test_dry_run_deletes_nothing_and_summary_is_compact(tmp_path: Path) -> None:
    receipt, plan, artifact = _effect(tmp_path)
    code, out, err = _run(["--effect-receipt", str(receipt), "--rollback-plan", str(plan), "--output-dir-scope", str(tmp_path), "--dry-run", "--summary"])
    assert code == 0, err
    payload = json.loads(out)
    assert payload["dry_run"] is True
    assert payload["would_delete_exact_artifact"] is True
    assert payload["real_rollback_performed"] is False
    assert artifact.exists()


def test_default_deletes_exact_artifact_and_keeps_sibling(tmp_path: Path) -> None:
    receipt, plan, artifact = _effect(tmp_path)
    sibling = tmp_path / "sibling.txt"
    sibling.write_text("keep", encoding="utf-8")
    code, out, err = _run(["--effect-receipt", str(receipt), "--rollback-plan", str(plan), "--output-dir-scope", str(tmp_path), "--summary"])
    assert code == 0, err
    payload = json.loads(out)
    assert payload["real_rollback_performed"] is True
    assert payload["file_delete_performed"] is True
    assert payload["exact_artifact_only"] is True
    assert payload["general_cleanup_performed"] is False
    assert payload["recursive_delete_performed"] is False
    assert payload["wildcard_delete_performed"] is False
    assert payload["unrelated_file_delete_performed"] is False
    assert not artifact.exists()
    assert sibling.read_text(encoding="utf-8") == "keep"


def test_refuses_digest_mismatch_outside_scope_and_directory(tmp_path: Path) -> None:
    receipt, plan, artifact = _effect(tmp_path)
    artifact.write_text("changed", encoding="utf-8")
    code, _out, _err = _run(["--effect-receipt", str(receipt), "--rollback-plan", str(plan), "--output-dir-scope", str(tmp_path), "--summary"])
    assert code == 1
    artifact.write_text("x", encoding="utf-8")
    code, _out, err = _run(["--effect-receipt", str(receipt), "--rollback-plan", str(plan), "--output-dir-scope", str(tmp_path / "other"), "--summary"])
    assert code == 2
    assert "output_path_outside_scope" in err
    artifact.unlink()
    artifact.mkdir()
    code, _out, _err = _run(["--effect-receipt", str(receipt), "--rollback-plan", str(plan), "--output-dir-scope", str(tmp_path), "--summary"])
    assert code == 1
