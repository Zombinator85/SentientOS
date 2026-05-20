import json
from pathlib import Path
from scripts.run_operator_confirmed_preflight import main


def _write(p: Path, obj: dict):
    p.write_text(json.dumps(obj), encoding='utf-8')


def test_script_summary_and_output(tmp_path: Path, capsys) -> None:
    ar = tmp_path/'ar.json'; pp = tmp_path/'p.json'; out = tmp_path/'out.json'
    _write(ar, {"status":"admission_run_accepted","packet":{"admission_run_packet_id":"r","admission_run_packet_digest":"d","work_item_id":"w1","admission_controller_invoked":True,"workspace_change_set_admission_status":"admission_accepted"}})
    _write(pp, {"work_item_id":"w1","declared_target_count":1,"proposed_targets":[{"target_id":"a","relative_target_path":"docs/a.txt","operation":"create_file","declared_payload_digest":"sha256:a"}]})
    code = main(['--admission-run', str(ar), '--proposal', str(pp), '--workspace-root', str(tmp_path), '--summary', '--output', str(out)])
    assert code in (0,2)
    assert 'preflight_run_' in capsys.readouterr().out
    assert out.exists()


def test_script_review_only_zero(tmp_path: Path) -> None:
    ar = tmp_path/'ar.json'; pp = tmp_path/'p.json'
    _write(ar, {"status":"admission_run_accepted","packet":{"admission_run_packet_id":"r","admission_run_packet_digest":"d","work_item_id":"w1","admission_controller_invoked":False,"workspace_change_set_admission_status":"admission_accepted"}})
    _write(pp, {"work_item_id":"w1","declared_target_count":0,"proposed_targets":[]})
    assert main(['--admission-run', str(ar), '--proposal', str(pp), '--workspace-root', str(tmp_path), '--review-only']) == 0
