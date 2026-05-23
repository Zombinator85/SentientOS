import json
import subprocess
import sys


def test_script_summary_and_output(tmp_path):
    digest = tmp_path / "d.json"
    digest.write_text(json.dumps({"digest": {"review_digest_id": "a", "review_digest_digest": "d", "digest_status": "lifecycle_attestation_review_digest_clear", "reviewer_posture": "reviewer_can_accept_index"}}), encoding="utf-8")
    out = tmp_path / "o.json"
    cmd = [sys.executable, "scripts/build_work_item_lifecycle_attestation_review_digest_index.py", "--review-digest", str(digest), "--summary", "--output", str(out), "--no-require-clear"]
    c = subprocess.run(cmd, check=False, text=True, capture_output=True)
    assert c.returncode == 0
    assert "aggregate_reviewer_posture" in c.stdout
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "lifecycle_attestation_review_digest_index_ready"
