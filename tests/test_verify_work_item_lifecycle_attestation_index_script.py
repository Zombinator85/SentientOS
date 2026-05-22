from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_work_item_lifecycle_attestation_index import main


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_script_summary_and_output(tmp_path: Path, capsys) -> None:
    idx = tmp_path / "index.json"
    _write(idx, {"index": {"attestation_index_id": "idx1", "attestation_index_digest": "dig1", "index_status": "lifecycle_attestation_index_ready", "indexed_count": 0, "entries": [], "duplicate_count": 0, "duplicate_keys": [], "skipped_count": 0, "skipped_inputs": []}})
    out = tmp_path / "out.json"
    code = main(["--attestation-index", str(idx), "--output", str(out), "--summary"])
    assert code == 0
    assert out.exists()
    assert "status=lifecycle_attestation_index_verification_passed" in capsys.readouterr().out
