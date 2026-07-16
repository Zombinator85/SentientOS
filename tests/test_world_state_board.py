from datetime import datetime, timezone
from dataclasses import replace
from sentientos.world_state_board import WorldStateBoardBuilder, validate_snapshot, diff_snapshots

def test_world_state_snapshot_boundaries_and_authority_false():
    b=WorldStateBoardBuilder(clock=lambda: datetime(2026,1,1,tzinfo=timezone.utc))
    s=b.build([
        {"source_kind":"control_plane_decision","source_id":"r","subject_id":"req","stage":"admission","disposition":"allow","observed_at":"2026-01-01T00:00:00+00:00"},
        {"source_kind":"fulfillment","source_id":"e","subject_id":"req","stage":"execution","disposition":"recorded","effect_claimed":True,"effect_proven":False},
    ])
    assert not any(s.authority.values())
    ent=s.entities[0]
    stages={p.stage:p.disposition for p in ent.stage_postures}
    assert stages["proposal"] == "unknown"
    assert stages["admission"] == "allow"
    assert s.summary.unproven_effect_claims == 1

def test_conflicts_order_independent_and_staleness():
    recs=[{"source_kind":"control_plane_decision","source_id":"a","subject_id":"x","stage":"admission","disposition":"deny","observed_at":"2025-12-25T00:00:00+00:00"},{"source_kind":"control_plane_decision","source_id":"b","subject_id":"x","stage":"admission","disposition":"allow","observed_at":"2026-01-01T00:00:00+00:00"}]
    b=WorldStateBoardBuilder(clock=lambda: datetime(2026,1,2,tzinfo=timezone.utc))
    c1=[c.conflict_type for c in b.build(recs).conflicts]
    c2=[c.conflict_type for c in b.build(list(reversed(recs))).conflicts]
    assert c1 == c2 == ["allow_deny"]
    assert b.build(recs).summary.counts["staleness_posture"]["expired"] == 1

def test_identity_ignores_custody_but_binds_semantics_and_nested_validation():
    base={"source_kind":"capability_registry","source_id":"cap","subject_id":"cap","stage":"observation","disposition":"implemented","observed_at":"one","absolute_path":"/tmp/a","payload":{"x":1}}
    b=WorldStateBoardBuilder()
    s1=b.build([base]); s2=b.build([{**base,"observed_at":"two","absolute_path":"/elsewhere"}]); s3=b.build([{**base,"payload":{"x":2}}])
    assert [f.fact_id for f in s1.facts] == [f.fact_id for f in s2.facts]
    assert [f.fact_id for f in s1.facts] != [f.fact_id for f in s3.facts]
    assert validate_snapshot(s1).valid
    bad=replace(s1, facts=tuple(replace(s1.facts[0], disposition="tampered") for _ in [0]))
    assert not validate_snapshot(bad).valid

def test_delta_disappearance_not_deletion():
    b=WorldStateBoardBuilder(); before=b.build([{"source_kind":"capability_registry","source_id":"a"}]); after=b.build([])
    d=diff_snapshots(before, after)
    assert d.changes[0]["change"] == "disappearance_from_current_observation"
    assert d.changes[0]["deletion_claimed"] is False
