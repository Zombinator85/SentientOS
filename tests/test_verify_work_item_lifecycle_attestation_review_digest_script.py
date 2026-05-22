from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_work_item_lifecycle_attestation_review_digest import main


def test_summary_and_output(tmp_path: Path, capsys: object) -> None:
    digest = tmp_path / "digest.json"
    index = tmp_path / "index.json"
    report = tmp_path / "report.json"
    output = tmp_path / "out.json"
    digest.write_text(json.dumps({"digest": {"review_digest_id": "d1", "review_digest_digest": "dd1", "attestation_index_id": "i1", "attestation_index_digest": "id1", "index_verification_report_id": "r1", "index_verification_report_digest": "rd1", "digest_status": "lifecycle_attestation_review_digest_clear", "reviewer_posture": "reviewer_can_accept_index", "work_item_count": 0, "sealed_count": 0, "attention_required_count": 0, "blocked_count": 0, "contradicted_count": 0, "warning_codes": [], "entries": []}}), encoding="utf-8")
    index.write_text(json.dumps({"index": {"attestation_index_id": "i1", "attestation_index_digest": "id1", "index_status": "lifecycle_attestation_index_ready", "indexed_count": 0, "entries": []}}), encoding="utf-8")
    report.write_text(json.dumps({"report": {"index_verification_report_id": "r1", "index_verification_report_digest": "rd1", "verification_status": "lifecycle_attestation_index_verification_passed", "warning_codes": [], "blocker_codes": [], "contradiction_codes": []}}), encoding="utf-8")
    rc = main(["--review-digest", str(digest), "--attestation-index", str(index), "--index-verification", str(report), "--summary", "--output", str(output)])
    out = capsys.readouterr().out  # type: ignore[attr-defined]
    assert rc == 0
    assert "status=lifecycle_attestation_review_digest_verification_passed" in out
    assert output.exists()
