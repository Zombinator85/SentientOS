import json
from pathlib import Path

from scripts.build_work_item_lifecycle_attestation_index import main


def test_script_summary_and_output(tmp_path: Path) -> None:
    b = tmp_path / "b.json"
    o = tmp_path / "o.json"
    b.write_text(json.dumps({"bundle": {"final_attestation_bundle_id": "b1", "final_attestation_bundle_digest": "d1", "work_item_id": "w1", "attestation_status": "lifecycle_final_attestation_sealed"}}), encoding="utf-8")
    code = main(["--attestation-bundle", str(b), "--output", str(o), "--summary"])
    assert code == 0
    text = o.read_text(encoding="utf-8")
    assert "attestation_index_digest" in text
