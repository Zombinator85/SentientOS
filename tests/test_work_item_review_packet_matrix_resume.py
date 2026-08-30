from __future__ import annotations

import json
from pathlib import Path
import sys
import pytest

from scripts.run_work_item_review_packet_matrix import MatrixCommand, run_resumable_matrix
pytestmark = pytest.mark.no_legacy_skip


def _commands(marker: Path) -> list[MatrixCommand]:
    return [MatrixCommand(f"lane_{n}", (sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).open('a').write('{n}\\n')")) for n in range(3)]


def test_matrix_checkpoints_after_each_lane(tmp_path: Path) -> None:
    report = run_resumable_matrix(commands=_commands(tmp_path / "runs"), checkpoint=tmp_path / "c.json", repo=Path("."))
    assert report["status"] == "matrix_passed" and report["next_lane_index"] == 3


def test_matrix_resume_skips_exact_completed_lanes(tmp_path: Path) -> None:
    marker = tmp_path / "runs"; checkpoint = tmp_path / "c.json"
    run_resumable_matrix(commands=_commands(marker), checkpoint=checkpoint, repo=Path("."))
    run_resumable_matrix(commands=_commands(marker), checkpoint=checkpoint, resume_from=checkpoint, repo=Path("."))
    assert marker.read_text().splitlines() == ["0", "1", "2"]


def test_matrix_resume_rejects_workspace_change(tmp_path: Path) -> None:
    checkpoint = tmp_path / "c.json"; run_resumable_matrix(commands=_commands(tmp_path / "runs"), checkpoint=checkpoint)
    data = json.loads(checkpoint.read_text()); data["workspace_binding"]["binding_digest"] = "changed"
    base = {k: v for k, v in data.items() if k != "checkpoint_digest"}
    from scripts.run_work_item_review_packet_matrix import _digest
    data["checkpoint_digest"] = _digest(base); checkpoint.write_text(json.dumps(data))
    assert run_resumable_matrix(commands=_commands(tmp_path / "runs"), checkpoint=tmp_path / "out", resume_from=checkpoint)["status"] == "matrix_resume_blocked"


def test_matrix_resume_rejects_command_manifest_change(tmp_path: Path) -> None:
    checkpoint = tmp_path / "c.json"; run_resumable_matrix(commands=_commands(tmp_path / "runs"), checkpoint=checkpoint)
    changed = _commands(tmp_path / "runs"); changed[1] = MatrixCommand("lane_1", (sys.executable, "-c", "pass"))
    assert run_resumable_matrix(commands=changed, checkpoint=tmp_path / "out", resume_from=checkpoint)["status"] == "matrix_resume_blocked"


def test_matrix_timeout_preserves_completed_lane_checkpoint(tmp_path: Path) -> None:
    commands = [MatrixCommand("one", (sys.executable, "-c", "pass")), MatrixCommand("two", (sys.executable, "-c", "import time; time.sleep(2)"))]
    report = run_resumable_matrix(commands=commands, checkpoint=tmp_path / "c.json", command_timeout_seconds=1)
    assert report["status"] == "matrix_timed_out" and report["completed_labels"] == ["one"]
    assert report["results"][-1]["label"] == "two"
    assert report["results"][-1]["exit_reason"] in {"process_tree_terminated", "process_tree_killed_after_grace"}
    persisted=json.loads((tmp_path / "c.json").read_text())
    assert persisted["completion_status"] == "matrix_timed_out" and persisted["active_lane"] is None


def test_optional_diagnostic_timeout_is_explicit_nonproof_not_success(tmp_path: Path) -> None:
    command=MatrixCommand("diagnostic",(sys.executable,"-c","import threading; threading.Event().wait()"),required=False,
                          proof_required=False,execution_required=False,diagnostic_only=True,nonexecution_allowed=True)
    report=run_resumable_matrix(commands=[command],checkpoint=tmp_path/"c.json",command_timeout_seconds=1)
    result=report["results"][0]
    assert report["status"]=="matrix_timed_out"
    assert report["required_failure_count"]==0
    assert result["proof_status"]=="timed-out" and result["diagnostic_only"] is True


def test_progress_and_checkpoint_name_active_lane(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    checkpoint=tmp_path/"c.json"
    report=run_resumable_matrix(commands=[MatrixCommand("named_lane",(sys.executable,"-c","pass"))],
                                checkpoint=checkpoint,progress=True)
    assert report["status"]=="matrix_passed"
    assert "[matrix] start 1/1 named_lane" in capsys.readouterr().out
    assert json.loads(checkpoint.read_text())["active_lane"] is None


def test_completed_passing_matrix_reuses_without_execution(tmp_path: Path) -> None:
    test_matrix_resume_skips_exact_completed_lanes(tmp_path)


def test_failed_required_lane_cannot_be_relabelled_passed(tmp_path: Path) -> None:
    commands = [MatrixCommand("bad", (sys.executable, "-c", "raise SystemExit(1)"))]
    checkpoint = tmp_path / "c.json"; assert run_resumable_matrix(commands=commands, checkpoint=checkpoint)["status"] == "matrix_failed"
    assert run_resumable_matrix(commands=commands, checkpoint=tmp_path / "out", resume_from=checkpoint)["status"] == "matrix_resume_blocked"
