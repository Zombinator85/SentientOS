from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_health_snapshot import (
    CodexWorkcellHealthSnapshotError,
    CodexWorkcellHealthSnapshotRequest,
    build_codex_workcell_health_snapshot,
    render_codex_workcell_health_snapshot_markdown,
)


def _write(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def test_snapshot_without_inputs_marks_all_not_provided() -> None:
    snap = build_codex_workcell_health_snapshot()
    assert snap["metadata_only"] is True
    assert len(snap["generated_from_inputs"]) == 10
    assert all(not item["provided"] for item in snap["generated_from_inputs"])
    assert snap["architecture_summary"] == {"provided": False}


def test_architecture_json_is_summarized(tmp_path: Path) -> None:
    arch = _write(tmp_path / "arch.json", {"workcell_architecture_id": "a", "components": [{"component_id": "f", "authority_level": "transition_authority"}, {"component_id": "r", "authority_level": "review_only"}], "flows": [{"flow_id": "x"}], "future_integration_points": [{"integration_id": "i"}], "sentientos_mount_alignment": {"/vow": {"purpose": "v", "components": []}}})
    snap = build_codex_workcell_health_snapshot(CodexWorkcellHealthSnapshotRequest(architecture_json=str(arch)))
    assert snap["architecture_summary"]["component_count"] == 2
    assert snap["architecture_summary"]["transition_authority_components"] == ["f"]
    assert snap["architecture_summary"]["mount_alignment_keys"] == ["/vow"]


def test_matrix_json_is_proof_signal_only(tmp_path: Path) -> None:
    matrix = _write(tmp_path / "matrix.json", {"status": "failed", "required_count": 3, "diagnostic_count": 2, "nonproof_count": 1, "blocked_lane_count": 4})
    snap = build_codex_workcell_health_snapshot(CodexWorkcellHealthSnapshotRequest(matrix_json=str(matrix)))
    assert snap["proof_summary"]["matrix_status"] == "failed"
    assert snap["proof_summary"]["required_failure_count"] == 3
    assert snap["proof_summary"]["proof_signal_only"] is True


def test_finalizer_and_guard_statuses_are_observed_not_decisions(tmp_path: Path) -> None:
    pre = _write(tmp_path / "pre.json", {"decision": {"status": "ready_to_commit"}, "evidence_freshness": {"rerun_required": True, "terminal_refresh_status": "stale"}})
    pr = _write(tmp_path / "pr.json", {"status": "ready_for_pr_metadata"})
    guard = _write(tmp_path / "guard.json", {"status": "pr_metadata_guard_ready"})
    snap = build_codex_workcell_health_snapshot(CodexWorkcellHealthSnapshotRequest(pre_commit_finalizer_json=str(pre), pr_metadata_finalizer_json=str(pr), pr_metadata_guard_json=str(guard)))
    assert snap["authority_summary"]["pre_commit_finalizer_status"] == "ready_to_commit"
    assert snap["authority_summary"]["authority_observed_from_inputs_only"] is True
    assert "ready_to_commit" not in snap
    assert snap["non_authority_posture"]["health_snapshot_does_not_decide_readiness"] is True


def test_evidence_index_doctor_and_sidecar_are_summarized(tmp_path: Path) -> None:
    life = _write(tmp_path / "life.json", {"overall_lifecycle_status": "lifecycle_ready"})
    doctor = _write(tmp_path / "doctor.json", {"overall_doctor_status": "doctor_ready", "next_safe_action": "review"})
    index = _write(tmp_path / "index.json", {"evidence_index_id": "idx", "artifacts": [{"role": "matrix"}], "artifact_roles_present": ["matrix"], "artifact_roles_missing": ["doctor_report"]})
    sidecar = _write(tmp_path / "sidecar.json", {"provenance_version": "v1", "rendered_markdown_digest": "abc"})
    snap = build_codex_workcell_health_snapshot(CodexWorkcellHealthSnapshotRequest(lifecycle_summary_json=str(life), lifecycle_doctor_json=str(doctor), evidence_index_json=str(index), evidence_appendix_sidecar_json=str(sidecar)))
    assert snap["evidence_summary"]["doctor_status"] == "doctor_ready"
    assert snap["evidence_summary"]["artifact_count"] == 1
    assert snap["provenance_summary"]["rendered_markdown_digest"] == "abc"


def test_doctrine_map_is_doctrine_only(tmp_path: Path) -> None:
    doctrine = _write(tmp_path / "doctrine.json", {"doctrine_map_id": "d", "traits": {"a": "b"}, "rail_mappings": [{"rail_id": "r"}]})
    snap = build_codex_workcell_health_snapshot(CodexWorkcellHealthSnapshotRequest(beneficial_trait_doctrine_json=str(doctrine)))
    assert snap["doctrine_summary"]["trait_count"] == 1
    assert snap["doctrine_summary"]["doctrine_only"] is True
    assert snap["doctrine_summary"]["not_model_training"] is True


def test_raw_byte_digests_and_sizes_are_recorded(tmp_path: Path) -> None:
    path = tmp_path / "matrix.json"
    raw = b'{"status":"ok"}\n'
    path.write_bytes(raw)
    snap = build_codex_workcell_health_snapshot(CodexWorkcellHealthSnapshotRequest(matrix_json=str(path)))
    rec = next(r for r in snap["generated_from_inputs"] if r["input_id"] == "matrix_json")
    assert rec["digest"] == hashlib.sha256(raw).hexdigest()
    assert rec["byte_size"] == len(raw)


def test_invalid_json_and_missing_path_fail_cleanly(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"; bad.write_text("{", encoding="utf-8")
    with pytest.raises(CodexWorkcellHealthSnapshotError, match="invalid_json"):
        build_codex_workcell_health_snapshot(CodexWorkcellHealthSnapshotRequest(matrix_json=str(bad)))
    with pytest.raises(CodexWorkcellHealthSnapshotError, match="missing_json"):
        build_codex_workcell_health_snapshot(CodexWorkcellHealthSnapshotRequest(matrix_json=str(tmp_path / "missing.json")))


def test_pressure_future_mount_determinism_and_markdown(tmp_path: Path) -> None:
    matrix = _write(tmp_path / "matrix.json", {"status": "failed", "required_count": 1, "diagnostic_count": 1})
    req = CodexWorkcellHealthSnapshotRequest(matrix_json=str(matrix))
    first = build_codex_workcell_health_snapshot(req)
    second = build_codex_workcell_health_snapshot(req)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert {m["mount"] for m in first["sentientos_mount_snapshot"]} == {"/vow", "/glow", "/pulse", "/daemon", "/ledger"}
    assert all(item["active_authority"] is False for item in first["future_integration_snapshot"])
    assert first["observed_pressure_signals"] == second["observed_pressure_signals"]
    md1 = render_codex_workcell_health_snapshot_markdown(first)
    md2 = render_codex_workcell_health_snapshot_markdown(first)
    assert md1 == md2
    assert md1.startswith("# Codex Workcell Health Snapshot")


def test_non_authority_posture_fields_true() -> None:
    posture = build_codex_workcell_health_snapshot()["non_authority_posture"]
    assert posture
    assert all(value is True for value in posture.values())
