from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.embodiment_self_observation import (
    AvatarBodyManifest, EmbodimentEvidenceError, EmbodimentEvidenceOwner,
    EmbodimentObservation, score_structured_assessment, semantic_digest,
)
from sentientos.longitudinal_self_model import LongitudinalSelfModelOwner
from sentientos.world_state_board import WorldStateBoardBuilder, diff_snapshots
from sentientosd import RuntimeMaintenanceSurfaces

NOW = "2035-01-01T00:00:00+00:00"


def manifest(generation: int = 1) -> AvatarBodyManifest:
    return AvatarBodyManifest("primary:body", "avatar-a", "sha256:" + "a" * 64, "glb", "rig-r1",
                              "sha256:" + "b" * 64, "godot:avatar-state:v1", "right-handed-y-up",
                              ("root", "head"), ("neutral", "smile"), ("idle", "wave"), (),
                              ("camera",), ("avatar_pose",), generation, None, "operator-import")


def observation(evidence_class: str, subject: str, payload: dict, *, source: str | None = None,
                freshness: str = "fresh", posture: str = "synthetic_test", observed_at: str = NOW) -> EmbodimentObservation:
    body = {"class": evidence_class, "subject": subject, "payload": payload, "time": observed_at}
    return EmbodimentObservation(source or f"test:{evidence_class}:{subject}", "fixture:v1",
                                 semantic_digest(body), observed_at, "synthetic", freshness, posture,
                                 evidence_class, subject, evidence_class, payload)


def snapshot(items):
    return WorldStateBoardBuilder(clock=lambda: datetime.fromisoformat(items[0].observed_at)).build(
        EmbodimentEvidenceOwner(items).world_state_records())


def test_manifest_and_command_observation_are_mechanically_distinct(tmp_path):
    body = manifest()
    items = [observation("body_manifest", "avatar", dict(body.__dict__)),
             observation("avatar_commanded_state", "avatar", {"commanded_pose": "wave"}),
             observation("avatar_renderer_reported_state", "avatar", {"renderer_reported_pose": "idle"}),
             observation("avatar_independently_observed_state", "avatar", {"observed_pose": "idle"})]
    board = snapshot(items)
    assert {fact.source.kind for fact in board.facts} == {"embodiment"}
    payloads = [fact.payload for fact in board.facts]
    assert any(p.get("commanded_pose") == "wave" for p in payloads)
    assert not any(p.get("observed_pose") == "wave" for p in payloads)
    reconciliation = LongitudinalSelfModelOwner(tmp_path / "self").reconcile(board, tick_id="tick-a")
    values = {(claim.predicate, claim.value) for claim in reconciliation.claims}
    assert ("embodiment.commanded_pose", "wave") in values
    assert ("embodiment.renderer_reported_pose", "idle") in values
    assert ("embodiment.observed_pose", "idle") in values
    assert all(not any(claim.authority.values()) for claim in reconciliation.claims)


def test_sentientosd_opt_in_and_absence_are_explicit(tmp_path):
    inert = RuntimeMaintenanceSurfaces(tmp_path, runtime_state_root=tmp_path / "inert")
    inert.build_world_state_board(tick_id=NOW)
    assert not inert.current_world_state_snapshot.facts
    owner = EmbodimentEvidenceOwner([observation("sensor_observation", "camera", {"present": True, "healthy": True})])
    composed = RuntimeMaintenanceSurfaces(tmp_path, runtime_state_root=tmp_path / "composed",
                                          embodiment_evidence_owner=owner)
    composed.build_world_state_board(tick_id=NOW)
    assert {fact.source.kind for fact in composed.current_world_state_snapshot.facts} == {"embodiment"}


def test_baseline_perturbation_restoration_and_prior_tick_firewall(tmp_path):
    baseline = snapshot([observation("sensor_observation", "camera", {"present": True, "healthy": True}, observed_at="2035-01-01T00:00:00+00:00")])
    perturbed = snapshot([observation("sensor_observation", "camera", {"present": True, "healthy": False}, observed_at="2035-01-01T00:01:00+00:00")])
    restored = snapshot([observation("sensor_observation", "camera", {"present": True, "healthy": True}, observed_at="2035-01-01T00:02:00+00:00")])
    assert diff_snapshots(baseline, perturbed).changes
    assert [f.payload.get("healthy") for f in baseline.facts] == [f.payload.get("healthy") for f in restored.facts]
    owner = LongitudinalSelfModelOwner(tmp_path / "self")
    a = owner.reconcile(baseline, tick_id="tick-a")
    prior_at_b = owner.cognitive_projection(before_tick="tick-b", max_claims=32,
                                             allowed_predicates=("embodiment.sensor_health",))
    assert prior_at_b and prior_at_b.source_reconciliation_id == a.reconciliation_id
    b = owner.reconcile(perturbed, tick_id="tick-b")
    assert owner.cognitive_projection(before_tick="tick-b", max_claims=32,
                                      allowed_predicates=("embodiment.sensor_health",)).source_reconciliation_id == a.reconciliation_id
    c = owner.reconcile(restored, tick_id="tick-c")
    assert c.generation == 3 and b.generation == 2
    current = [claim for claim in c.claims if claim.predicate == "embodiment.sensor_health" and claim.status == "current"]
    assert current and current[0].value is True and current[0].supersedes
    assert owner.reconstruct().reconciliation_id == c.reconciliation_id


def test_false_proprioception_contract_rejections_and_fulfillment_boundary():
    with pytest.raises(EmbodimentEvidenceError, match="sensor_health_requires_presence"):
        observation("sensor_observation", "camera", {"healthy": True}).validate()
    with pytest.raises(EmbodimentEvidenceError, match="synthetic_evidence_cannot_claim_production"):
        observation("sensor_observation", "camera", {"present": True}, posture="synthetic_test").__class__(
            "x", "fixture:v1", "sha256:x", NOW, "production", "fresh", "synthetic_test",
            "sensor_observation", "camera", "sensor", {"present": True}).validate()
    with pytest.raises(EmbodimentEvidenceError, match="authority_or_identity_claim_forbidden"):
        observation("avatar_commanded_state", "avatar", {"commanded_pose": "wave", "authority": True}).validate()
    same = observation("sensor_observation", "camera", {"present": True})
    changed = EmbodimentObservation(**{**same.__dict__, "source_digest": "sha256:changed"})
    with pytest.raises(EmbodimentEvidenceError, match="source_identity_digest_changed"):
        EmbodimentEvidenceOwner((same, changed)).world_state_records()
    command_only = snapshot([observation("avatar_commanded_state", "avatar", {"commanded_pose": "wave"})])
    assert not any(f.effect_proven or "observed_pose" in f.payload for f in command_only.facts)
    renderer = snapshot([observation("avatar_renderer_reported_state", "avatar", {"renderer_reported_pose": "wave"})])
    assert not any(f.effect_proven for f in renderer.facts)


def test_same_class_conflict_staleness_and_external_scoring(tmp_path):
    board = snapshot([
        observation("avatar_independently_observed_state", "avatar", {"observed_pose": "wave"}, source="observer:a", freshness="stale"),
        observation("avatar_independently_observed_state", "avatar", {"observed_pose": "idle"}, source="observer:b"),
    ])
    reconciliation = LongitudinalSelfModelOwner(tmp_path).reconcile(board, tick_id="tick")
    claims = [c for c in reconciliation.claims if c.predicate == "embodiment.observed_pose"]
    assert len(claims) == 2 and all(c.status == "contradicted" for c in claims)
    result = score_structured_assessment(expected={"pose": "idle", "sensor": "camera"},
                                         answers={"pose": "idle", "sensor": "camera",
                                                  "source_ids": ["observer:b"]},
                                         supported_sources=("observer:b",))
    assert result["supported_correct"] == 2 and result["supported_incorrect"] == 0
    assert result["source_provenance_correct"] is True
