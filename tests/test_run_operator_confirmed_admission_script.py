import json
from pathlib import Path
from scripts.run_operator_confirmed_admission import main


def _write(p: Path, obj: dict):
    p.write_text(json.dumps(obj), encoding='utf-8')


def test_script_summary_and_output(tmp_path: Path, capsys) -> None:
    rr = tmp_path/'rr.json'; pp = tmp_path/'p.json'; out = tmp_path/'out.json'
    _write(rr, {"status":"admission_review_ready","packet":{"admission_review_packet_id":"r","admission_review_packet_digest":"d","work_item_id":"w1","required_operator_acknowledgements":["ok"]}})
    _write(pp, {"declared_target_count":1,"proposed_targets":[{"target_id":"a","relative_target_path":"docs/a.txt","operation":"create_file","declared_payload_byte_count":1,"declared_payload_digest":"sha256:a"}]})
    assert main(['--operator-review', str(rr), '--proposal', str(pp), '--summary', '--output', str(out)]) == 0
    assert 'admission_run_accepted' in capsys.readouterr().out
    assert out.exists()


def test_script_nonzero_blocked(tmp_path: Path) -> None:
    rr = tmp_path/'rr.json'; pp = tmp_path/'p.json'
    _write(rr, {"status":"admission_review_manual_review_required","packet":{"admission_review_packet_id":"r","admission_review_packet_digest":"d","work_item_id":"w1","required_operator_acknowledgements":["ok"]}})
    _write(pp, {"declared_target_count":1,"proposed_targets":[]})
    assert main(['--operator-review', str(rr), '--proposal', str(pp)]) == 2
