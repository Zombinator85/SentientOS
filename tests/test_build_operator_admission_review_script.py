import json
from pathlib import Path
from scripts.build_operator_admission_review import main


def test_script_summary_and_output(tmp_path: Path, capsys) -> None:
    in_file = tmp_path/'promo.json'; out = tmp_path/'out.json'
    in_file.write_text(json.dumps({'promotion_dossier_id':'x','promotion_dossier_digest':'d','work_item_id':'w1','promotion_status':'promotion_ready_for_admission_review','artifact_records':[{'digest':'1'}]}), encoding='utf-8')
    assert main(['--promotion-dossier', str(in_file), '--summary', '--output', str(out)]) == 0
    text = capsys.readouterr().out
    assert 'admission_review_ready' in text
    assert out.exists()


def test_nonzero_blocked(tmp_path: Path) -> None:
    in_file = tmp_path/'promo.json'
    in_file.write_text(json.dumps({'promotion_dossier_id':'x','promotion_dossier_digest':'d','work_item_id':'w1','promotion_status':'promotion_blocked_authority'}), encoding='utf-8')
    assert main(['--promotion-dossier', str(in_file)]) == 2
