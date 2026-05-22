import json

from scripts.build_work_item_lifecycle_attestation_review_digest import main


def test_script_summary_and_output(tmp_path) -> None:
    index = tmp_path / "index.json"
    report = tmp_path / "report.json"
    out = tmp_path / "digest.json"
    index.write_text(json.dumps({"index": {"attestation_index_id": "idx1", "attestation_index_digest": "didx", "index_status": "lifecycle_attestation_index_ready", "entries": [{"entry_id": "e1", "work_item_id": "w1", "attestation_status": "lifecycle_final_attestation_sealed", "attention_required": False, "sort_key": "w1"}]}}), encoding="utf-8")
    report.write_text(json.dumps({"report": {"index_verification_report_id": "r1", "index_verification_report_digest": "dr1", "attestation_index_id": "idx1", "attestation_index_digest": "didx", "verification_status": "lifecycle_attestation_index_verification_passed", "blocker_codes": [], "warning_codes": [], "contradiction_codes": []}}), encoding="utf-8")
    rc = main(["--attestation-index", str(index), "--index-verification", str(report), "--summary", "--output", str(out)])
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "lifecycle_attestation_review_digest_clear"


def test_script_nonzero_blocked(tmp_path) -> None:
    index = tmp_path / "index.json"
    report = tmp_path / "report.json"
    index.write_text(json.dumps({"index": {"attestation_index_id": "idx1", "attestation_index_digest": "didx", "index_status": "lifecycle_attestation_index_blocked", "entries": []}}), encoding="utf-8")
    report.write_text(json.dumps({"report": {"index_verification_report_id": "r1", "index_verification_report_digest": "dr1", "attestation_index_id": "idx1", "attestation_index_digest": "didx", "verification_status": "lifecycle_attestation_index_verification_passed", "blocker_codes": [], "warning_codes": [], "contradiction_codes": []}}), encoding="utf-8")
    assert main(["--attestation-index", str(index), "--index-verification", str(report)]) == 1
