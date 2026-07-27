from __future__ import annotations

import json
import subprocess

from sentientos.task_acceptance import verify


NODE = "tests/test_task_acceptance_verifier.py::test_valid_successful_path_verifies"


def _sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], text=True, capture_output=True, check=True).stdout.strip()


def _files(tmp_path, *, outcome="passed", selected=True, sha=None):
    sha = sha or _sha()
    provenance = tmp_path / "provenance.json"
    provenance.write_text(json.dumps({"git_sha": sha, "reporter_ok": True, "metrics_status": "ok", "selected_node_ids": [NODE] if selected else [], "node_outcomes": [{"node_id": NODE, "phase": "call", "outcome": outcome}]}), encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": "sentientos.task_acceptance:v1", "task_classification": "behavior_adding", "repository_sha": sha, "test_provenance_path": str(provenance), "required_nodes": [{"node_id": NODE, "rationale": "successful verifier path"}], "successful_path_nodes": [NODE]}), encoding="utf-8")
    return manifest, provenance


def test_valid_successful_path_verifies(tmp_path):
    manifest, provenance = _files(tmp_path)
    result = verify(manifest, provenance)
    assert result["status"] == "task_acceptance_ready"
    assert result["node_outcomes"][0]["passed"] is True
    assert result["manifest_digest"].startswith("sha256:")
    assert result["provenance_digest"].startswith("sha256:")


def test_missing_unexecuted_skipped_and_failed_nodes_block(tmp_path):
    for outcome, selected in [("passed", False), ("skipped", True), ("failed", True), ("xfailed", True)]:
        manifest, provenance = _files(tmp_path, outcome=outcome, selected=selected)
        assert verify(manifest, provenance)["status"] == "task_acceptance_blocked"


def test_stale_or_tampered_provenance_is_rejected(tmp_path):
    manifest, provenance = _files(tmp_path, sha="0" * 40)
    assert "repository_sha_mismatch" in verify(manifest, provenance)["reasons"]
    manifest, provenance = _files(tmp_path)
    payload = json.loads(provenance.read_text())
    payload["reporter_ok"] = False
    provenance.write_text(json.dumps(payload), encoding="utf-8")
    assert "reporter_incomplete" in verify(manifest, provenance)["reasons"]
