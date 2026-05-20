import json
from pathlib import Path

from scripts.build_operator_execution_review import main


def _w(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj), encoding="utf-8")


def test_cli_summary_and_output(tmp_path: Path, capsys) -> None:
    pre = tmp_path / "pre.json"; pro = tmp_path / "pro.json"; out = tmp_path / "out.json"
    _w(pre, {"status": "preflight_run_ready", "packet": {"work_item_id": "w1", "preflight_controller_invoked": True, "transaction_plan_ready": True}})
    _w(pro, {"work_item_id": "w1", "proposed_targets": []})
    code = main(["--preflight-run", str(pre), "--proposal", str(pro), "--summary", "--output", str(out)])
    assert code == 0
    assert "execution_review_ready" in capsys.readouterr().out
    assert out.exists()


def test_cli_exit_nonzero_for_blocked(tmp_path: Path) -> None:
    pre = tmp_path / "pre.json"; pro = tmp_path / "pro.json"
    _w(pre, {"status": "preflight_run_blocked_by_preflight", "packet": {"work_item_id": "w1", "preflight_controller_invoked": True, "transaction_plan_ready": False}})
    _w(pro, {"work_item_id": "w1", "proposed_targets": []})
    assert main(["--preflight-run", str(pre), "--proposal", str(pro)]) == 2
