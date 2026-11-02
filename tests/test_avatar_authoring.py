from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime
from dataclasses import replace
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.avatar_authoring import (
    AvatarAuthoringError, BackendIdentity, BLENDER_SUPPORTED_FORMATS, BLENDER_SUPPORTED_OPERATIONS,
    SyntheticArtifactInspector, SyntheticAuthoringBackend,
    adopt, adoption_observation, blender_readiness, build_admission, digest,
    compare_structure, genesis_adopt, lineage, load_pointer, renderer_handoff, rollback, run_workcell,
    BlenderArtifactInspector, BlenderBackend,
    primitive_mesh_vertex_count, successor_manifest, validate_plan,
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


@pytest.mark.parametrize("arguments,error",[
    ({"base_color":[0.1,0.2,0.3],"metallic":0.1,"roughness":0.5},"material_color_invalid"),
    ({"base_color":[0.1,0.2,0.3,float("nan")],"metallic":0.1,"roughness":0.5},"material_color_invalid"),
    ({"base_color":[0.1,0.2,1.1,1.0],"metallic":0.1,"roughness":0.5},"material_color_invalid"),
    ({"base_color":[0.1,0.2,0.3,1.0],"metallic":1.1,"roughness":0.5},"material_property_invalid"),
    ({"base_color":[0.1,0.2,0.3,1.0],"metallic":0.1,"roughness":-0.1},"material_property_invalid"),
])
def test_material_plan_parameters_are_finite_and_bounded(tmp_path,arguments,error):
    m=manifest(artifact(tmp_path/"material.glb")); value=plan(m)
    value["operations"]=[operation("material","create_material","Companion",arguments,{"exists":True})]
    with pytest.raises(AvatarAuthoringError,match=error): validate_plan(value)


def test_transform_plan_rejects_nonfinite_components(tmp_path):
    m=manifest(artifact(tmp_path/"material.glb")); value=plan(m)
    value["operations"]=[operation("move","set_transform","Body",
        {"location":[0.0,float("nan"),0.0]}, {})]
    with pytest.raises(AvatarAuthoringError,match="plan_vector_invalid"):
        validate_plan(value)


def test_blender_primitive_vertex_estimate_and_per_mesh_bound(tmp_path):
    m=manifest(artifact(tmp_path/"a.glb")); value=plan(m)
    mesh=operation("head","create_primitive_mesh","Head",{"primitive":"uv_sphere","vertices":128},{})
    value["operations"]=[mesh]
    with pytest.raises(AvatarAuthoringError,match="primitive_geometry_bound_exceeded"):
        validate_plan(value)
    assert primitive_mesh_vertex_count({"primitive":"uv_sphere","vertices":64})==1986


def test_authoring_plan_total_geometry_budget_is_bounded(tmp_path):
    m=manifest(artifact(tmp_path/"a.glb")); value=plan(m)
    value["operations"]=[operation(f"head-{index}","create_primitive_mesh",f"Head{index}",
        {"primitive":"uv_sphere","vertices":64},{}) for index in range(33)]
    with pytest.raises(AvatarAuthoringError,match="plan_geometry_budget_exceeded"):
        validate_plan(value)


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
    workspace=tmp_path/"workspace"
    result=blender_readiness(tmp_path/"missing-blender",driver,workspace)
    assert result["status"]=="blender_backend_unavailable" and not any(result["authority"].values()) and not result["mutation_performed"]
    assert not workspace.exists()


def test_blender_driver_capabilities_match_the_declared_backend() -> None:
    from scripts.avatar_blender_driver import SUPPORTED_OPERATIONS, _primitive_vertex_count

    assert SUPPORTED_OPERATIONS == BLENDER_SUPPORTED_OPERATIONS
    assert BLENDER_SUPPORTED_FORMATS == {"blend", "glb"}
    for primitive, vertices in (("cube", 32), ("plane", 32), ("uv_sphere", 32),
                                ("uv_sphere", 64), ("cylinder", 256), ("cone", 256)):
        args={"primitive":primitive,"vertices":vertices} if primitive in {"uv_sphere","cylinder","cone"} else {"primitive":primitive}
        assert _primitive_vertex_count(args)==primitive_mesh_vertex_count(args)


def test_blender_driver_rejects_shape_keys_without_geometry_edits_before_importing_bpy() -> None:
    from scripts.avatar_blender_driver import translate

    value={"schema_version":"sentientos.avatar_authoring_plan:v1","operations":[
        {"operation_id":"shape","kind":"create_shape_key","target":"Body","arguments":{}}]}
    with pytest.raises(ValueError,match="shape_key_arguments_invalid"):
        translate(value)


def test_shape_key_geometry_offsets_are_bounded_and_unique(tmp_path):
    source=artifact(tmp_path/"shape-key.glb")
    valid_plan=plan(manifest(source))
    next(item for item in valid_plan["operations"] if item["kind"]=="create_shape_key")["arguments"]["vertex_offsets"]=[
        {"vertex_index":2,"offset":[0.0,0.0,0.05]}]
    assert validate_plan(valid_plan)["plan_digest"].startswith("sha256:")
    for offsets,error in (
        ([{"vertex_index":2,"offset":[0.0,0.0,0.05]},{"vertex_index":2,"offset":[0.0,0.0,0.03]}],"shape_key_vertex_offsets_invalid"),
        ([{"vertex_index":4096,"offset":[0.0,0.0,0.05]}],"shape_key_vertex_offsets_invalid"),
        ([{"vertex_index":2,"offset":[0.0,0.0,0.26]}],"shape_key_vertex_offset_bound_exceeded"),
        ([{"vertex_index":2,"offset":[0.0,0.0,0.0]}],"shape_key_vertex_offset_bound_exceeded"),
    ):
        invalid=plan(manifest(source))
        target=next(item for item in invalid["operations"] if item["kind"]=="create_shape_key")
        target["arguments"]["vertex_offsets"]=offsets
        with pytest.raises(AvatarAuthoringError,match=error): validate_plan(invalid)


def test_bone_animation_contract_bounds_clip_and_keyframes(tmp_path):
    source=artifact(tmp_path/"animation.glb")
    checked=plan(manifest(source))
    valid_arguments={"animation":"wave","armature":"Rig","bone":"hand","fps":30,
        "keyframes":[{"frame":0,"rotation_degrees":[0.0,0.0,0.0]},
                      {"frame":30,"rotation_degrees":[0.0,0.0,45.0]}]}
    checked["operations"].append(operation("wave-clip","create_bone_animation","Rig",
        valid_arguments,{"animation":"wave"}))
    assert validate_plan(checked)["plan_digest"].startswith("sha256:")
    invalid_cases=(
        ({**valid_arguments,"fps":0},"bone_animation_fps_invalid"),
        ({**valid_arguments,"keyframes":[{"frame":0,"rotation_degrees":[0,0,0]},
            {"frame":0,"rotation_degrees":[0,0,45]}]},"bone_animation_keyframes_invalid"),
        ({**valid_arguments,"keyframes":[{"frame":0,"rotation_degrees":[0,0,0]},
            {"frame":30,"rotation_degrees":[0,0,181]}]},"bone_animation_rotation_bound_exceeded"),
        ({**valid_arguments,"keyframes":[{"frame":0,"rotation_degrees":[0,0,0]},
            {"frame":600,"rotation_degrees":[0,0,45]}]},"bone_animation_duration_bound_exceeded"),
    )
    for arguments,error in invalid_cases:
        invalid=plan(manifest(source))
        invalid["operations"].append(operation("wave-clip","create_bone_animation","Rig",arguments,
            {"animation":"wave"}))
        with pytest.raises(AvatarAuthoringError,match=error): validate_plan(invalid)


def test_blender_driver_independently_rejects_unbounded_bone_animation():
    from scripts.avatar_blender_driver import translate

    arguments={"animation":"wave","armature":"Rig","bone":"hand","fps":30,
        "keyframes":[{"frame":0,"rotation_degrees":[0,0,0]},
                      {"frame":30,"rotation_degrees":[0,0,45]}]}
    value={"schema_version":"sentientos.avatar_authoring_plan:v1","operations":[
        {"operation_id":"wave","kind":"create_bone_animation","target":"Rig",
         "arguments":arguments}]}
    assert len(translate(value))==1
    for invalid_arguments,error in (
        ({**arguments,"fps":61},"bone_animation_fps_invalid"),
        ({**arguments,"keyframes":[{"frame":0,"rotation_degrees":[0,0,0]},
            {"frame":30,"rotation_degrees":[0,0,181]}]},"bone_animation_rotation_bound_exceeded"),
    ):
        invalid={"schema_version":"sentientos.avatar_authoring_plan:v1","operations":[
            {"operation_id":"wave","kind":"create_bone_animation","target":"Rig",
             "arguments":invalid_arguments}]}
        with pytest.raises(ValueError,match=error): translate(invalid)


@pytest.mark.parametrize("arguments,error",[
    ({"base_color":[0.1,0.2,0.3],"metallic":0.1,"roughness":0.5},"material_color_invalid"),
    ({"base_color":[0.1,0.2,0.3,float("nan")],"metallic":0.1,"roughness":0.5},"material_color_invalid"),
    ({"base_color":[0.1,0.2,0.3,1.0],"metallic":0.1,"roughness":1.01},"material_property_invalid"),
])
def test_blender_driver_independently_rejects_invalid_material_values(arguments,error):
    from scripts.avatar_blender_driver import translate

    value={"schema_version":"sentientos.avatar_authoring_plan:v1","operations":[
        {"operation_id":"ceramic","kind":"create_material","target":"Ceramic","arguments":arguments}]}
    with pytest.raises(ValueError,match=error):
        translate(value)


def test_structure_comparison_reports_unrequested_new_bones():
    checked=validate_plan({"schema_version":"sentientos.avatar_authoring_plan:v1","plan_id":"rig",
        "installation_body_id":"install","body_id":"body","predecessor_generation":1,
        "predecessor_artifact_digest":"sha256:artifact","predecessor_manifest_digest":"sha256:manifest",
        "proposed_by":"test","operations":[operation("root","create_bone","Rig",{}, {"bone":"root"})]})
    before={"inspection_digest":"before","bones":{},"objects":{},"armatures":{}}
    after={"inspection_digest":"after","bones":{"Rig/root":{},"Rig/Bone":{}},
        "objects":{},"armatures":{}}
    compared=compare_structure(before,checked,after)
    assert compared["unexpected_changes"]==["bone:Rig/Bone"]


def test_configured_blender_creates_and_independently_inspects_non_adopted_rig(tmp_path):
    executable=shutil.which("blender")
    if executable is None:
        pytest.skip("Blender is unavailable in this validation environment")
    source=tmp_path/"predecessor.blend"
    home=tmp_path/"home"; cache=tmp_path/"cache"
    home.mkdir(); cache.mkdir()
    created=subprocess.run([executable,"--background","--factory-startup","--python-expr",
        f"import bpy; bpy.ops.wm.save_as_mainfile(filepath={str(source)!r})"],
        check=False,capture_output=True,text=True,timeout=45,
        env={"PATH":os.defpath,"HOME":str(home),"XDG_CACHE_HOME":str(cache),"LC_ALL":"C"})
    assert created.returncode==0 and source.is_file(), created.stderr[-2000:]

    import hashlib
    source_digest="sha256:"+hashlib.sha256(source.read_bytes()).hexdigest()
    old=AvatarBodyManifest("installation:diagnostic","avatar:smoke",source_digest,"blend",
        "rig:empty",digest({}),"renderer:diagnostic","right-handed-y-up",(),(),(),(),(),
        ("avatar_pose",),1,None,"non-adopted-blender-test")
    value={"schema_version":"sentientos.avatar_authoring_plan:v1","plan_id":"blender-smoke",
        "installation_body_id":old.installation_body_id,"body_id":"avatar:smoke",
        "predecessor_generation":1,"predecessor_artifact_digest":source_digest,
        "predecessor_manifest_digest":old.semantic_digest,"proposed_by":"test",
        "operations":[
            operation("rig","create_armature","SentientRig",{}, {"exists":True}),
            operation("root","create_bone","SentientRig",{"parent":None,"head":[0,0,-1],"tail":[0,0,0]}, {"bone":"root"}),
            operation("upper","create_bone","SentientRig",{"parent":"root","head":[0,0,0],"tail":[0,0,1]}, {"bone":"upper"}),
            operation("head","create_primitive_mesh","CompanionHead",{"primitive":"uv_sphere","vertices":32}, {}),
            operation("skin","bind_armature","CompanionHead",{"armature":"SentientRig"}, {"armature":"SentientRig"}),
            operation("ceramic","create_material","CompanionCeramic",
                {"base_color":[0.11,0.57,0.65,1.0],"metallic":0.18,"roughness":0.32}, {"exists":True}),
            operation("head-material","assign_material","CompanionHead",
                {"material":"CompanionCeramic"}, {"material":"CompanionCeramic"}),
            operation("smile","create_shape_key","CompanionHead",{"shape_key":"smile","vertex_offsets":[
                {"vertex_index":208,"offset":[0.0,0.0,0.04]},
                {"vertex_index":209,"offset":[0.0,0.0,0.08]},
                {"vertex_index":210,"offset":[0.0,0.0,0.04]},
                {"vertex_index":268,"offset":[0.0,0.0,0.04]},
                {"vertex_index":269,"offset":[0.0,0.0,0.08]},
                {"vertex_index":270,"offset":[0.0,0.0,0.04]}]}, {"shape_key":"smile"}),
            operation("wave","create_bone_animation","SentientRig",{
                "animation":"wave","armature":"SentientRig","bone":"upper","fps":30,
                "keyframes":[
                    {"frame":0,"rotation_degrees":[0.0,0.0,0.0]},
                    {"frame":8,"rotation_degrees":[0.0,0.0,55.0]},
                    {"frame":16,"rotation_degrees":[0.0,0.0,-55.0]},
                    {"frame":24,"rotation_degrees":[0.0,0.0,0.0]},
                ]}, {"animation":"wave"}),
        ]}
    pointer={"body_generation":1,"artifact_sha256":source_digest,"manifest_digest":old.semantic_digest}
    driver=Path(__file__).parents[1]/"scripts"/"avatar_blender_driver.py"
    inspector_driver=Path(__file__).parents[1]/"scripts"/"avatar_blender_inspector.py"
    backend=BlenderBackend(Path(executable),driver)
    inspector=BlenderArtifactInspector(Path(executable),inspector_driver)
    workspace=(tmp_path/"workcells"/"smoke").resolve()
    successor=workspace/"output"/"successor.blend"
    checked=validate_plan(value)
    admission=build_admission(admission_id="development-smoke",work_id="smoke",pointer=pointer,
        plan=checked,workspace=workspace,backend=backend.identity,output=successor,
        operator_approval="test-only; no adoption")
    result=run_workcell(current_pointer=pointer,predecessor_manifest=old,predecessor=source,
        plan_value=value,admission=admission,workspace_root=tmp_path/"workcells",backend=backend,
        inspector=inspector,work_id="smoke")

    assert result["receipt"]["result_posture"]=="candidate_validated"
    assert result["comparison"]["counts"]["satisfied"]==9
    assert result["comparison"]["unexpected_changes"]==[]
    assert sorted(result["successor_inspection"]["bones"])==["SentientRig/root","SentientRig/upper"]
    head=result["successor_inspection"]["objects"]["CompanionHead"]
    assert head["vertex_count"]==482
    assert set(head["vertex_group_names"])=={"root","upper"}
    assert head["materials"]==["CompanionCeramic"]
    material=result["successor_inspection"]["materials"]["CompanionCeramic"]
    assert material["base_color"]==pytest.approx([0.11,0.57,0.65,1.0],abs=1e-4)
    assert material["metallic"]==pytest.approx(0.18,abs=1e-4)
    assert material["roughness"]==pytest.approx(0.32,abs=1e-4)
    assert result["receipt"]["backend_identity"]["evidence_posture"]=="configured_candidate_tool"
    assert not any(result["receipt"]["authority"].values())
    assert "smile" in result["successor_inspection"]["shape_keys"]["CompanionHead"]
    shape_geometry=result["successor_inspection"]["shape_key_geometry"]["CompanionHead"]["smile"]
    assert shape_geometry["changed_vertex_count"]==6
    assert shape_geometry["maximum_vertex_delta"]==pytest.approx(0.08,abs=1e-4)
    wave_clip=result["successor_inspection"]["channels"]["wave"]
    assert wave_clip["animation_clip"]=="wave"
    assert wave_clip["control"]=="SentientRig/upper"
    assert wave_clip["keyframe_count"]>=12

def test_configured_blender_authors_and_reopens_glb_candidate(tmp_path):
    executable=shutil.which("blender")
    if executable is None:
        pytest.skip("Blender is unavailable in this validation environment")
    source=tmp_path/"predecessor.glb"
    home=tmp_path/"home"; cache=tmp_path/"cache"
    home.mkdir(); cache.mkdir()
    created=subprocess.run([executable,"--background","--factory-startup","--python-expr",
        f"import bpy; bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.mesh.primitive_cube_add(); bpy.ops.export_scene.gltf(filepath={str(source)!r}, export_format='GLB')"],
        check=False,capture_output=True,text=True,timeout=45,
        env={"PATH":os.defpath,"HOME":str(home),"XDG_CACHE_HOME":str(cache),"LC_ALL":"C"})
    assert created.returncode==0 and source.is_file(), created.stderr[-2000:]

    import hashlib
    source_digest="sha256:"+hashlib.sha256(source.read_bytes()).hexdigest()
    old=AvatarBodyManifest("installation:diagnostic","avatar:glb-smoke",source_digest,"glb",
        "rig:empty",digest({}),"renderer:diagnostic","right-handed-y-up",(),(),(),(),(),
        ("avatar_pose",),1,None,"non-adopted-glb-test")
    value={"schema_version":"sentientos.avatar_authoring_plan:v1","plan_id":"glb-smoke",
        "installation_body_id":old.installation_body_id,"body_id":"avatar:glb-smoke",
        "predecessor_generation":1,"predecessor_artifact_digest":source_digest,
        "predecessor_manifest_digest":old.semantic_digest,"proposed_by":"test",
        "operations":[
            operation("rig","create_armature","SentientRig",{}, {"exists":True}),
            operation("root","create_bone","SentientRig",{"parent":None,"head":[0,0,-1],"tail":[0,0,0]}, {"bone":"root"}),
            operation("upper","create_bone","SentientRig",{"parent":"root","head":[0,0,0],"tail":[0,0,1]}, {"bone":"upper"}),
            operation("head","create_primitive_mesh","CompanionHead",{"primitive":"uv_sphere","vertices":32}, {}),
            operation("skin","bind_armature","CompanionHead",{"armature":"SentientRig"}, {"armature":"SentientRig"}),
            operation("ceramic","create_material","CompanionCeramic",
                {"base_color":[0.11,0.57,0.65,1.0],"metallic":0.18,"roughness":0.32}, {"exists":True}),
            operation("head-material","assign_material","CompanionHead",
                {"material":"CompanionCeramic"}, {"material":"CompanionCeramic"}),
            operation("smile","create_shape_key","CompanionHead",{"shape_key":"smile","vertex_offsets":[
                {"vertex_index":208,"offset":[0.0,0.0,0.04]},
                {"vertex_index":209,"offset":[0.0,0.0,0.08]},
                {"vertex_index":210,"offset":[0.0,0.0,0.04]},
                {"vertex_index":268,"offset":[0.0,0.0,0.04]},
                {"vertex_index":269,"offset":[0.0,0.0,0.08]},
                {"vertex_index":270,"offset":[0.0,0.0,0.04]}]}, {"shape_key":"smile"}),
            operation("wave-clip","create_bone_animation","SentientRig",{
                "animation":"wave","armature":"SentientRig","bone":"upper","fps":30,
                "keyframes":[
                    {"frame":0,"rotation_degrees":[0.0,0.0,0.0]},
                    {"frame":8,"rotation_degrees":[0.0,0.0,55.0]},
                    {"frame":16,"rotation_degrees":[0.0,0.0,-55.0]},
                    {"frame":24,"rotation_degrees":[0.0,0.0,0.0]},
                ]}, {"animation":"wave"}),
        ]}
    pointer={"body_generation":1,"artifact_sha256":source_digest,"manifest_digest":old.semantic_digest}
    driver=Path(__file__).parents[1]/"scripts"/"avatar_blender_driver.py"
    inspector_driver=Path(__file__).parents[1]/"scripts"/"avatar_blender_inspector.py"
    backend=BlenderBackend(Path(executable),driver)
    inspector=BlenderArtifactInspector(Path(executable),inspector_driver)
    workspace=(tmp_path/"workcells"/"glb-smoke").resolve()
    successor=workspace/"output"/"successor.glb"
    checked=validate_plan(value)
    admission=build_admission(admission_id="development-glb-smoke",work_id="glb-smoke",pointer=pointer,
        plan=checked,workspace=workspace,backend=backend.identity,output=successor,
        operator_approval="test-only; no adoption")
    result=run_workcell(current_pointer=pointer,predecessor_manifest=old,predecessor=source,
        plan_value=value,admission=admission,workspace_root=tmp_path/"workcells",backend=backend,
        inspector=inspector,work_id="glb-smoke")

    assert result["receipt"]["result_posture"]=="candidate_validated", result["comparison"]
    assert result["comparison"]["counts"]["satisfied"]==9
    assert result["comparison"]["unexpected_changes"]==[]
    assert sorted(result["successor_inspection"]["bones"])==["SentientRig/root","SentientRig/upper"]
    head=result["successor_inspection"]["objects"]["CompanionHead"]
    assert head["vertex_count"]==482
    assert set(head["vertex_group_names"])=={"root","upper"}
    assert head["materials"]==["CompanionCeramic"]
    material=result["successor_inspection"]["materials"]["CompanionCeramic"]
    assert material["base_color"]==pytest.approx([0.11,0.57,0.65,1.0],abs=1e-4)
    assert material["metallic"]==pytest.approx(0.18,abs=1e-4)
    assert material["roughness"]==pytest.approx(0.32,abs=1e-4)
    assert result["receipt"]["backend_identity"]["evidence_posture"]=="configured_candidate_tool"
    assert not any(result["receipt"]["authority"].values())
    assert "smile" in result["successor_inspection"]["shape_keys"]["CompanionHead"]
    shape_geometry=result["successor_inspection"]["shape_key_geometry"]["CompanionHead"]["smile"]
    assert shape_geometry["changed_vertex_count"]==6
    assert shape_geometry["maximum_vertex_delta"]==pytest.approx(0.08,abs=1e-4)
    wave_clip=result["successor_inspection"]["channels"]["wave"]
    assert wave_clip["animation_clip"]=="wave"
    assert wave_clip["control"]=="SentientRig/upper"
    assert wave_clip["keyframe_count"]>=12

    godot=shutil.which("godot")
    if godot is None:
        godot=next((str(path) for path in (Path("/usr/local/bin/godot"),Path("/usr/bin/godot"),
            Path("/usr/bin/godot4")) if path.is_file() and os.access(path,os.X_OK)),None)
    if godot is not None:
        project=tmp_path/"godot-project"
        shutil.copytree(Path(__file__).parents[1]/"godot_avatar_demo",project,
            ignore=shutil.ignore_patterns(".godot","*.uid"))
        shutil.copyfile(Path(result["successor_path"]),project/"candidate.glb")
        script="res://tests/candidate_body_probe.gd"
        candidate_evidence={"result_posture":result["receipt"]["result_posture"],
            "artifact_sha256":result["receipt"]["successor_artifact"]["sha256"],
            "receipt_digest":result["receipt"]["receipt_digest"],
            "authority":result["receipt"]["authority"],
            "body_id":result["receipt"]["body_id"],
            "predecessor_generation":result["receipt"]["predecessor_generation"]}
        godot_home=tmp_path/"godot-home"; godot_cache=tmp_path/"godot-cache"
        godot_font=tmp_path/"godot-font-cache"
        for directory in (godot_home,godot_cache,godot_font): directory.mkdir()
        godot_env={"PATH":os.defpath,"HOME":str(godot_home),"XDG_CACHE_HOME":str(godot_cache),
            "FONTCONFIG_CACHE_DIR":str(godot_font)}
        imported=subprocess.run([godot,"--headless","--path",str(project),"--editor","--quit"],
            check=False,capture_output=True,text=True,timeout=60,env=godot_env)
        assert imported.returncode==0, imported.stdout+imported.stderr
        loaded=subprocess.run([godot,"--headless","--path",str(project),"--quit-after","300",
            "--script",script,"--",json.dumps(candidate_evidence,separators=(",",":"))],
            check=False,capture_output=True,text=True,timeout=60,env=godot_env)
        assert loaded.returncode==0, loaded.stdout+loaded.stderr
        assert "sentientos_candidate_renderer_probe_passed" in loaded.stdout, loaded.stdout+loaded.stderr
        assert "sentientos_authored_motion_clip_playing name=wave" in loaded.stdout
        report_line=next(line for line in loaded.stdout.splitlines()
            if line.startswith("sentientos_candidate_renderer_report_json:"))
        report=json.loads(report_line.split(":",1)[1])
        candidate_state=report["candidate_state"]
        assert candidate_state["identity"]["artifact_sha256"]==candidate_evidence["artifact_sha256"]
        assert candidate_state["identity"]["adopted"] is False
        assert candidate_state["motion"]["status"]=="applied"
        assert candidate_state["motion"]["motion_source"]=="authored_gltf_animation"
        assert candidate_state["motion"]["animation_clip"]=="wave"
        assert candidate_state["expression"]["status"]=="blend_shape_applied"
        assert candidate_state["expression"]["shape"]=="smile"
        assert candidate_state["expression"]["weight"]==pytest.approx(0.8,abs=1e-6)
        assert candidate_state["visemes"]["status"]=="unsupported"
        report_payload={key:value for key,value in report.items() if key!="source_digest"}
        expected_report_digest="sha256:"+hashlib.sha256(json.dumps(report_payload,
            sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")).hexdigest()
        assert report["source_digest"]==expected_report_digest
        assert report["schema_version"]=="sentientos.experimental_candidate_avatar_renderer_report:v1"
        assert report["effect_proven"] is False
        assert report["independent_observation"] is False


def test_run_workcell_rejects_unavailable_backend_capability_before_workspace_creation(tmp_path):
    source=artifact(tmp_path/"body.glb"); old=manifest(source)
    pointer={"artifact_sha256":old.source_artifact_digest,"manifest_digest":old.semantic_digest}
    class LimitedBackend:
        identity=BackendIdentity("limited","test","1",None,None,"driver",("set_transform",),"synthetic_test")
        def author(self,*_args,**_kwargs): raise AssertionError("unsupported authoring ran")
    workspace=tmp_path/"uncreated-workspace"
    with pytest.raises(AvatarAuthoringError,match="authoring_backend_capability_mismatch"):
        run_workcell(current_pointer=pointer,predecessor_manifest=old,predecessor=source,
            plan_value=plan(old),admission={},workspace_root=workspace,backend=LimitedBackend(),
            inspector=SyntheticArtifactInspector(),work_id="work-unsupported")
    assert not workspace.exists()


def test_blender_workcell_rejects_gltf_sidecars_before_workspace_creation(tmp_path):
    source=artifact(tmp_path/"body.glb"); old=replace(manifest(source),asset_format="gltf")
    pointer={"artifact_sha256":old.source_artifact_digest,"manifest_digest":old.semantic_digest}
    backend=BackendIdentity("configured_blender","blender-cli-static-driver","1",None,None,"driver",
        tuple(sorted(BLENDER_SUPPORTED_OPERATIONS)),"production")
    class ConfiguredBackend:
        identity=backend
    workspace=tmp_path/"uncreated-workspace"
    with pytest.raises(AvatarAuthoringError,match="blender_asset_format_unsupported"):
        run_workcell(current_pointer=pointer,predecessor_manifest=old,predecessor=source,
            plan_value=plan(old),admission={},workspace_root=workspace,backend=ConfiguredBackend(),
            inspector=SyntheticArtifactInspector(),work_id="work-unsupported-format")
    assert not workspace.exists()


def test_cli_selects_explicit_blender_author_and_inspector_paths(monkeypatch):
    from scripts import avatar_authoring as cli

    observed=[]
    class Backend:
        def __init__(self, executable, driver, *, expected_sha256=None):
            observed.append(("author", executable, driver, expected_sha256))
    class Inspector:
        def __init__(self, executable, driver, *, expected_sha256=None):
            observed.append(("inspector", executable, driver, expected_sha256))
    monkeypatch.setattr(cli, "BlenderBackend", Backend)
    monkeypatch.setattr(cli, "BlenderArtifactInspector", Inspector)
    args=cli.parser().parse_args(["run-one","--pointer","p","--manifest","m","--predecessor","a.blend",
        "--plan","plan","--workspace-root","work","--work-id","w","--admission-id","admit",
        "--approval","development","--output","out","--backend","blender","--blender","/opt/blender",
        "--driver","/repo/driver.py","--inspector-driver","/repo/inspect.py","--executable-sha256","sha256:abc"])
    backend,inspector=cli._authoring_backends(args)
    assert isinstance(backend,Backend) and isinstance(inspector,Inspector)
    assert observed==[("author",Path("/opt/blender"),Path("/repo/driver.py"),"sha256:abc"),
        ("inspector",Path("/opt/blender"),Path("/repo/inspect.py"),"sha256:abc")]
