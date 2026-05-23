from __future__ import annotations

import json
import subprocess
import sys


def test_script_summary_and_output(tmp_path) -> None:
    idx = tmp_path / "index.json"
    out = tmp_path / "out.json"
    idx.write_text(json.dumps({"index": {"review_digest_index_id": "i", "review_digest_index_digest": "d", "index_status": "lifecycle_attestation_review_digest_index_ready", "indexed_count": 0, "entries": [], "duplicate_count": 0, "duplicate_keys": [], "skipped_count": 0, "skipped_inputs": [], "aggregate_reviewer_posture": "reviewer_can_accept_all"}}), encoding="utf-8")
    cmd = [sys.executable, "scripts/verify_work_item_lifecycle_attestation_review_digest_index.py", "--review-digest-index", str(idx), "--summary", "--output", str(out)]
    cp = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert cp.returncode == 0
    assert "verification_status=" in cp.stdout
    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "lifecycle_attestation_review_digest_index_verification_passed"
