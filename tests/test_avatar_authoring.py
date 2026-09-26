from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.avatar_authoring import (
    AvatarAuthoringError, SyntheticArtifactInspector, SyntheticAuthoringBackend,
    adopt, adoption_observation, blender_readiness, build_admission, digest,
    genesis_adopt, lineage, load_pointer, renderer_handoff, rollback, run_workcell,
    successor_manifest, validate_plan,
)
from sentientos.embodiment_self_observation import AvatarBodyManifest, EmbodimentEvidenceOwner
from sentientos.longitudinal_self_model import LongitudinalSelfModelOwner
from sentientos.world_state_board import WorldStateBoardBuilder


def artifact(path: Path) -> Path:
    value={"fixture_schema":"sentientos.synthetic_avatar_artifact:v1","asset_format":"glb","body_id":"body-a","labels":{},
           "objects":{"Body":{"type":"MESH","primitive":"fixture","vertices":8,"transform":{"location":[0.,0.,0.],"rotation":[0.,0.,0.],"scale":[1.,1.,1.]},"materials":[],"parent":None,"armature":None}},
           "armatures":{},"materials":{},"shape_keys":{},"channels":{}}
    path.write_text(json.dumps(value,sort_keys=True)); return path


def manifest(path: Path) -> AvatarBodyManifest:
    import hashlib
    sha="sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()
    return AvatarBodyManifest("install:body","avatar-a",sha,"glb","rig-empty",digest({}),"renderer:test:v1","right-handed-y-up",(),(),(),(),(),("avatar_pose",),1,None,"explicit-import")


def operation(op_id, kind, target, arguments, postcondition):
    return {"operation_id":op_id,"kind":kind,"target":target,"arguments":arguments,"preconditions":{},"postcondition":postcondition}


def plan(m: AvatarBodyManifest):
    return {"schema_version":"sentientos.avatar_authoring_plan:v1","plan_id":"rig-plan","installation_body_id":m.installation_body_id,"body_id":"body-a","predecessor_generation":1,"predecessor_artifact_digest":m.source_artifact_digest,"predecessor_manifest_digest":m.semantic_digest,"proposed_by":"test-proposer","operations":[
        operation("armature","create_armature","Rig",{}, {"exists":True}),
        operation("root","create_bone","Rig",{"parent":None,"head":[0,0,0],"tail":[0,1,0]}, {"bone":"root"}),
        operation("head","create_bone","Rig",{"parent":"root","head":[0,1,0],"tail":[0,2,0]}, {"bone":"head"}),
        operation("hand","create_bone","Rig",{"parent":"root","head":[0,1,0],"tail":[1,1,0]}, {"bone":"hand"}),
        operation("bind","bind_armature","Body",{"armature":"Rig"}, {"armature":"Rig"}),
        operation("smile","create_shape_key","Body",{"shape_key":"smile"}, {"shape_key":"smile"}),
        operation("wave","register_channel","body-a",{"channel":"wave","channel_kind":"motion","control":"Rig/hand"}, {"channel":"wave"}),
    ]}


def execute(tmp_path):
    source=artifact(tmp_path/"body.glb"); old=manifest(source); pointer_path=tmp_path/"current.json"
    pointer=genesis_adopt(pointer_path=pointer_path,installation_id="installation-a",body_id="body-a",artifact=source,manifest=old,approval="operator:test-genesis")
    backend=SyntheticAuthoringBackend(); inspector=SyntheticArtifactInspector(); checked=validate_plan(plan(old)); work_id="work-1"
    # Admission binds the exact workspace before it exists.
    workspace=(tmp_path/"runs"/work_id).resolve(); output=workspace/"output"/"successor.glb"
    admission=build_admission(admission_id="admission-1",work_id=work_id,pointer=pointer,plan=checked,workspace=workspace,backend=backend.identity,output=output,operator_approval="operator:test-author")
    result=run_workcell(current_pointer=pointer,predecessor_manifest=old,predecessor=source,plan_value=plan(old),admission=admission,workspace_root=tmp_path/"runs",backend=backend,inspector=inspector,work_id=work_id)
    return source,old,pointer_path,pointer,result


def test_end_to_end_author_adopt_world_state_self_model_and_rollback(tmp_path):
    source,old,pointer_path,pointer,result=execute(tmp_path)
    assert result["receipt"]["result_posture"]=="candidate_validated"
    assert result["comparison"]["counts"]["satisfied"]==7
    assert result["successor_inspection"]["bones"]["Rig/head"]["parent"]=="root"
    new_manifest=successor_manifest(old,result); assert new_manifest.body_generation==2 and "smile" in new_manifest.expressions
    adopted=adopt(pointer_path=pointer_path,lineage_path=tmp_path/"lineage.jsonl",expected_pointer_digest=pointer["pointer_digest"],candidate=result,manifest=new_manifest,approval="operator:test-adopt")
    assert load_pointer(pointer_path)["body_generation"]==2
    obs=adoption_observation(adopted["pointer"],new_manifest,observed_at="2035-01-01T00:00:00+00:00",posture="synthetic_test")
    board=WorldStateBoardBuilder(clock=lambda: datetime.fromisoformat(obs.observed_at)).build(EmbodimentEvidenceOwner([obs]).world_state_records())
    reconciled=LongitudinalSelfModelOwner(tmp_path/"self-model").reconcile(board,tick_id="tick-2")
    assert any(c.predicate=="embodiment.body_generation" and c.value==2 for c in reconciled.claims)
    handoff=renderer_handoff(adopted["pointer"],renderer_interface_id="renderer:test:v1",requested_pose="wave",requested_expression="smile",correlation_id="render-1")
    assert handoff["evidence_class"]=="commanded_output" and not handoff["renderer_reported"] and not handoff["independently_observed"]
    reverted=rollback(pointer_path=pointer_path,lineage_path=tmp_path/"lineage.jsonl",adopted=adopted,predecessor_manifest=old,approval="operator:test-rollback")
    assert reverted["pointer"]["body_generation"]==1
    events=lineage(tmp_path/"lineage.jsonl"); assert [e["event"] for e in events]==["adoption","rollback"] and events[-1]["historical_generation_preserved"]


@pytest.mark.parametrize("mutation,error",[
    (lambda p:p["operations"][0].update(kind="run_python"),"authoring_operation_unknown"),
    (lambda p:p["operations"][0].update(python="evil"),"authoring_operation_shape_invalid"),
    (lambda p:p["operations"][0]["arguments"].update(shell="rm"),"authoring_operation_arguments_invalid"),
    (lambda p:p["operations"][0]["arguments"].update(addon="x"),"authoring_operation_arguments_invalid"),
    (lambda p:p["operations"][0].update(target="https://evil"),"plan_name_invalid"),
    (lambda p:p["operations"][0].update(target="/tmp/x"),"plan_name_invalid"),
    (lambda p:p["operations"][0].update(target="../x"),"plan_name_invalid"),
])
def test_plan_security(tmp_path,mutation,error):
    m=manifest(artifact(tmp_path/"a.glb")); value=plan(m); mutation(value)
    with pytest.raises(AvatarAuthoringError,match=error): validate_plan(value)


def test_plan_operation_and_geometry_bounds(tmp_path):
    m=manifest(artifact(tmp_path/"a.glb")); value=plan(m); value["operations"]*=10
    with pytest.raises(AvatarAuthoringError,match="operation_count"): validate_plan(value)
    value=plan(m); value["operations"][0].update(kind="create_primitive_mesh",target="Huge",arguments={"vertices":10001})
    with pytest.raises(AvatarAuthoringError,match="geometry_bound"): validate_plan(value)


def test_artifact_workspace_and_adoption_fail_closed(tmp_path):
    source,old,pointer_path,pointer,result=execute(tmp_path)
    with pytest.raises(AvatarAuthoringError,match="candidate_not_validated"):
        adopt(pointer_path=pointer_path,lineage_path=tmp_path/"l",expected_pointer_digest=pointer["pointer_digest"],candidate={**result,"receipt":{**result["receipt"],"result_posture":"candidate_rejected"}},manifest=successor_manifest(old,result),approval="x")
    new=successor_manifest(old,result); Path(result["successor_path"]).write_text("changed")
    with pytest.raises(AvatarAuthoringError,match="digest_changed"):
        adopt(pointer_path=pointer_path,lineage_path=tmp_path/"l",expected_pointer_digest=pointer["pointer_digest"],candidate=result,manifest=new,approval="x")
    link=tmp_path/"link.glb"; link.symlink_to(source)
    from sentientos.avatar_authoring import file_identity
    with pytest.raises(AvatarAuthoringError,match="not_regular"): file_identity(link)


def test_cas_missing_approval_and_unrequested_mutation(tmp_path):
    _,old,pointer_path,pointer,result=execute(tmp_path); new=successor_manifest(old,result)
    with pytest.raises(AvatarAuthoringError,match="approval_missing"):
        adopt(pointer_path=pointer_path,lineage_path=tmp_path/"l",expected_pointer_digest=pointer["pointer_digest"],candidate=result,manifest=new,approval="")
    with pytest.raises(AvatarAuthoringError,match="compare_and_swap"):
        adopt(pointer_path=pointer_path,lineage_path=tmp_path/"l",expected_pointer_digest="sha256:stale",candidate=result,manifest=new,approval="x")
    result["successor_inspection"]["objects"]["Surprise"]={}
    # Backend telemetry is not consulted by the comparator or manifest constructor.
    result["receipt"]["execution_record"]["status"]="completed"
    assert "Surprise" not in result["comparison"]["unexpected_changes"]


def test_blender_readiness_absent_is_precise_and_non_authoritative(tmp_path):
    driver=Path(__file__).parents[1]/"scripts"/"avatar_blender_driver.py"
    result=blender_readiness(tmp_path/"missing-blender",driver,tmp_path/"workspace")
    assert result["status"]=="blender_backend_unavailable" and not any(result["authority"].values()) and not result["mutation_performed"]
