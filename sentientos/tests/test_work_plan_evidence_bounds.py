from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from sentientos.work_plan import (
    MAX_WORK_PLAN_EVIDENCE_INLINE_BINDING_BYTES,
    WORK_PLAN_EVIDENCE_DIR,
    WorkPlan,
    WorkPlanError,
    load_work_plan_evidence,
    persist_work_plan_evidence,
    work_plan_id_from_evidence,
)

pytestmark = pytest.mark.no_legacy_skip


def _large_projection_bound_plan() -> tuple[WorkPlan, dict[str, object]]:
    rows = []
    for index in range(320):
        suffix = f"{index:024x}"
        rows.append({
            "proposition_id": f"epistemic-proposition:{suffix}",
            "state_id": f"epistemic-state:{suffix}",
            "state_digest": "sha256:" + f"{index:064x}",
            "generation": 2,
            "update_event_id": f"epistemic-update:{suffix}",
            "update_tick": index + 1,
            "stance": "contested",
            "dependency_unresolved": False,
            "freshness": "current",
            "updated_at": "2026-01-01T00:00:00Z",
            "omission_reason": "projection_state_bound",
        })
    omitted_digest = "sha256:" + hashlib.sha256(json.dumps(
        rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    manifest = {
        "schema_version": "sentientos.epistemic_projection_omission_manifest:v1",
        "selection_policy": "latest_prior_state_by_proposition_id_ascending",
        "selection_limit": 1,
        "available_prior_state_count": len(rows) + 1,
        "selected_state_count": 1,
        "omitted_state_count": len(rows),
        "omitted_identity_digest": omitted_digest,
        "omitted_state_identities": rows,
    }
    review_scopes = {
        row["proposition_id"]: {
            "omitted_from_prior_projection": True,
            "omitted_state_identity": row,
        }
        for row in rows
    }
    evidence_binding: dict[str, object] = {
        "goal_graph_hash": "graph-digest",
        "allocation_artifact_path": "glow/forge/allocations/allocation.json",
        "projection_digest": "sha256:" + "a" * 64,
        "projection_omission_manifest": manifest,
        "review_scopes": review_scopes,
    }
    created_at = "2026-10-16T09:00:00Z"
    plan = WorkPlan(
        schema_version=1,
        plan_id=work_plan_id_from_evidence(
            created_at,
            str(evidence_binding["goal_graph_hash"]),
            str(evidence_binding["allocation_artifact_path"]),
            evidence_binding,
        ),
        created_at=created_at,
        context="bounded_prior_projection",
        selected_goals=(),
        tasks=(),
    )
    return plan, evidence_binding


def test_large_epistemic_evidence_round_trips_exactly_through_immutable_sidecar(
    tmp_path: Path,
) -> None:
    plan, evidence_binding = _large_projection_bound_plan()
    binding_bytes = json.dumps(
        evidence_binding, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    assert len(binding_bytes) > MAX_WORK_PLAN_EVIDENCE_INLINE_BINDING_BYTES

    path, digest = persist_work_plan_evidence(tmp_path, plan, evidence_binding)
    evidence_path = tmp_path / path
    stored = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert stored["schema_version"] == 2
    assert set(stored) == {
        "schema_version", "plan_id", "plan_digest",
        "evidence_binding_reference", "evidence_digest",
    }
    sidecars = list((tmp_path / WORK_PLAN_EVIDENCE_DIR).glob("binding_*.json"))
    assert len(sidecars) == 1
    assert sidecars[0].read_bytes() == binding_bytes
    assert stored["evidence_binding_reference"]["sha256"] == hashlib.sha256(
        binding_bytes).hexdigest()

    loaded = load_work_plan_evidence(tmp_path, plan)
    assert loaded["evidence_binding"] == evidence_binding
    assert loaded["evidence_digest"] == digest


def test_large_epistemic_evidence_sidecar_tampering_fails_closed(tmp_path: Path) -> None:
    plan, evidence_binding = _large_projection_bound_plan()
    persist_work_plan_evidence(tmp_path, plan, evidence_binding)
    sidecar = next((tmp_path / WORK_PLAN_EVIDENCE_DIR).glob("binding_*.json"))
    altered = bytearray(sidecar.read_bytes())
    altered[-2] ^= 1
    sidecar.write_bytes(altered)

    with pytest.raises(WorkPlanError, match="work_plan_evidence_binding_sidecar_digest_mismatch"):
        load_work_plan_evidence(tmp_path, plan)

def test_interrupted_sidecar_write_leaves_no_partial_canonical_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, evidence_binding = _large_projection_bound_plan()
    original_fsync = os.fsync

    def fail_before_sidecar_publication(_descriptor: int) -> None:
        raise OSError("simulated interruption before atomic sidecar publication")

    monkeypatch.setattr(os, "fsync", fail_before_sidecar_publication)
    with pytest.raises(WorkPlanError,
            match="work_plan_evidence_binding_sidecar_write_failed"):
        persist_work_plan_evidence(tmp_path, plan, evidence_binding)

    plan_key = hashlib.sha256(plan.plan_id.encode("utf-8")).hexdigest()
    evidence_dir = tmp_path / WORK_PLAN_EVIDENCE_DIR
    assert not (evidence_dir / f"binding_{plan_key}.json").exists()
    assert not (evidence_dir / f"evidence_{plan_key}.json").exists()
    assert not list(evidence_dir.glob(f".binding_{plan_key}.json.*.tmp"))

    monkeypatch.setattr(os, "fsync", original_fsync)
    evidence_path, digest = persist_work_plan_evidence(
        tmp_path, plan, evidence_binding)
    assert digest == load_work_plan_evidence(tmp_path, plan)["evidence_digest"]
    assert (tmp_path / evidence_path).is_file()


def test_interrupted_evidence_envelope_write_recovers_after_sidecar_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, evidence_binding = _large_projection_bound_plan()
    original_fsync = os.fsync
    fsync_calls = 0

    def fail_before_envelope_publication(descriptor: int) -> None:
        nonlocal fsync_calls
        fsync_calls += 1
        if fsync_calls == 3:
            raise OSError("simulated interruption before evidence envelope publication")
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_before_envelope_publication)
    with pytest.raises(WorkPlanError, match="work_plan_artifact_write_failed"):
        persist_work_plan_evidence(tmp_path, plan, evidence_binding)

    plan_key = hashlib.sha256(plan.plan_id.encode("utf-8")).hexdigest()
    evidence_dir = tmp_path / WORK_PLAN_EVIDENCE_DIR
    sidecar_path = evidence_dir / f"binding_{plan_key}.json"
    envelope_path = evidence_dir / f"evidence_{plan_key}.json"
    assert fsync_calls == 3
    assert sidecar_path.is_file()
    assert not envelope_path.exists()
    assert not list(evidence_dir.glob(f".binding_{plan_key}.json.*.tmp"))
    assert not list(evidence_dir.glob(f".evidence_{plan_key}.json.*.tmp"))

    expected_sidecar = json.dumps(
        evidence_binding, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    assert sidecar_path.read_bytes() == expected_sidecar

    monkeypatch.setattr(os, "fsync", original_fsync)
    evidence_path, digest = persist_work_plan_evidence(
        tmp_path, plan, evidence_binding)
    assert envelope_path == tmp_path / evidence_path
    assert load_work_plan_evidence(tmp_path, plan)["evidence_digest"] == digest

