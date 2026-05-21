import json
from pathlib import Path

from scripts.build_operator_lifecycle_closure_review import main


def _w(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj), encoding="utf-8")


def test_cli_summary_and_output(tmp_path: Path, capsys) -> None:
    ver = tmp_path / "ver.json"; pro = tmp_path / "pro.json"; out = tmp_path / "out.json"
    _w(ver, {"status": "verification_run_passed", "packet": {"work_item_id": "w1", "verification_controller_invoked": True}})
    _w(pro, {"work_item_id": "w1", "proposed_targets": []})
    code = main(["--verification-run", str(ver), "--proposal", str(pro), "--summary", "--output", str(out)])
    assert code == 0
    assert "closure_review_ready" in capsys.readouterr().out
    assert out.exists()


def test_cli_exit_nonzero_for_blocked(tmp_path: Path) -> None:
    ver = tmp_path / "ver.json"; pro = tmp_path / "pro.json"
    _w(ver, {"status": "verification_run_failed", "packet": {"work_item_id": "w1", "verification_controller_invoked": True}})
    _w(pro, {"work_item_id": "w1", "proposed_targets": []})
    assert main(["--verification-run", str(ver), "--proposal", str(pro)]) == 2
