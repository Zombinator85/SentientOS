import json

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentient_mesh import MeshJob, SentientMesh
from sentientos.autonomy.state import ContinuitySnapshot, ContinuityStateManager
from sentientos.gradient_contract import (
    GradientInvariantViolation,
    enforce_no_gradient_fields,
)


def test_enforce_no_gradient_fields_allows_clean_payload():
    payload = {"goal": {"status": "ok"}, "context": ["a", "b", {"nested": 1}]}
    enforce_no_gradient_fields(payload, context="unit-test:clean")


def test_enforce_no_gradient_fields_rejects_nested_gradient_field():
    payload = {"outer": {"Reward": 1}}
    with pytest.raises(GradientInvariantViolation, match="NO_GRADIENT_INVARIANT"):
        enforce_no_gradient_fields(payload, context="unit-test:nested")


def test_mesh_cycle_rejects_gradient_fields_in_job_payload(tmp_path):
    mesh = SentientMesh(transcripts_dir=tmp_path, voices=[])
    mesh.update_node("alpha", trust=1.0, load=0.1, capabilities=["sentient_script"])
    job = MeshJob(
        job_id="job-1",
        script={"goal": "steady", "loss": 0.4},
        prompt="steady",
        priority=1,
        requirements=("sentient_script",),
        metadata={},
    )
    with pytest.raises(GradientInvariantViolation, match="NO_GRADIENT_INVARIANT"):
        mesh.cycle([job])


def test_advisory_metadata_cannot_smuggle_gradient_fields(tmp_path):
    mesh = SentientMesh(transcripts_dir=tmp_path, voices=[])
    mesh.update_node("alpha", trust=1.0, load=0.1, capabilities=["sentient_script"])
    job = MeshJob(
        job_id="job-1",
        script={"goal": "steady"},
        prompt="steady",
        priority=1,
        requirements=("sentient_script",),
        metadata={"advisory": {"score": 0.8}},
    )
    with pytest.raises(GradientInvariantViolation, match="NO_GRADIENT_INVARIANT"):
        mesh.cycle([job])


def test_continuity_state_rejects_gradient_fields(tmp_path):
    path = tmp_path / "session.json"
    payload = {"curiosity_queue": [{"goal": {"id": "g1"}, "delta": 1.0}]}
    path.write_text(json.dumps(payload), encoding="utf-8")
    manager = ContinuityStateManager(path)
    with pytest.raises(GradientInvariantViolation, match="NO_GRADIENT_INVARIANT"):
        manager.load()


def test_continuity_state_save_blocks_gradient_fields(tmp_path):
    path = tmp_path / "session.json"
    manager = ContinuityStateManager(path)
    snapshot = ContinuitySnapshot(curiosity_queue=[{"goal": {"id": "g2", "reward": 1.0}}])
    with pytest.raises(GradientInvariantViolation, match="NO_GRADIENT_INVARIANT"):
        manager.save(snapshot)
