# mypy: disable-error-code="no-untyped-def,no-untyped-call,import-not-found"
"""Repository-owned Blender driver.  JSON plans contain no executable code."""
from __future__ import annotations
import hashlib, json, sys

SUPPORTED_OPERATIONS={"create_primitive_mesh","create_armature","create_bone","set_transform","bind_armature"}
MAX_PRIMITIVE_MESH_VERTICES=4096
MAX_PLAN_GEOMETRY_VERTICES=65536

def _digest(value): return "sha256:"+hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def _primitive_vertex_count(arguments):
    primitive=arguments.get("primitive","cube")
    if primitive in {"cube","plane"}: return 8 if primitive=="cube" else 4
    vertices=arguments.get("vertices",32)
    if type(vertices) is not int or not 3<=vertices<=256: raise ValueError("geometry_bound_exceeded")
    if primitive=="uv_sphere": return vertices*(max(4,vertices//2)-1)+2
    if primitive=="cylinder": return vertices*2
    if primitive=="cone": return vertices+1
    raise ValueError("primitive_kind_unsupported")
def validate_geometry_bounds(plan):
    total=0
    for operation in plan.get("operations",[]):
        if operation.get("kind")!="create_primitive_mesh": continue
        arguments=operation.get("arguments",{})
        if not isinstance(arguments,dict): raise ValueError("authoring_operation_arguments_invalid")
        estimate=_primitive_vertex_count(arguments)
        if estimate>MAX_PRIMITIVE_MESH_VERTICES: raise ValueError("primitive_geometry_bound_exceeded")
        total+=estimate
        if total>MAX_PLAN_GEOMETRY_VERTICES: raise ValueError("plan_geometry_budget_exceeded")
    return total
def translate(plan):
    allowed=SUPPORTED_OPERATIONS
    if plan.get("schema_version")!="sentientos.avatar_authoring_plan:v1" or any(op.get("kind") not in allowed for op in plan.get("operations",[])): raise ValueError("invalid_plan")
    validate_geometry_bounds(plan)
    return tuple((op["operation_id"],op["kind"],op["target"],dict(op["arguments"])) for op in plan["operations"])
def main(argv):
    try:
        separator=argv.index("--")
        plan_path,predecessor_path,output_path,claimed=argv[separator+1:]
    except (ValueError,TypeError):
        raise ValueError("driver_arguments_invalid") from None
    plan=json.load(open(plan_path,encoding="utf-8")); embedded=plan.pop("plan_digest",None)
    if embedded!=claimed or _digest(plan)!=claimed: raise ValueError("plan_digest_mismatch")
    operations=translate(plan)
    import bpy  # imported only inside Blender
    predecessor_format=predecessor_path.rsplit(".",1)[-1].lower()
    if predecessor_format=="glb":
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=predecessor_path)
    elif predecessor_format!="blend":
        raise ValueError("asset_format_unsupported")
    results=[]
    for op_id,kind,target,args in operations:
        # Keep the real backend limited to inspectable mesh and rig operations.
        if kind=="create_primitive_mesh":
            primitive=args.get("primitive","cube")
            vertices=args.get("vertices",32)
            _primitive_vertex_count(args)
            if primitive=="cube": bpy.ops.mesh.primitive_cube_add()
            elif primitive=="uv_sphere": bpy.ops.mesh.primitive_uv_sphere_add(segments=vertices,ring_count=max(4,vertices//2))
            elif primitive=="cylinder": bpy.ops.mesh.primitive_cylinder_add(vertices=vertices)
            elif primitive=="cone": bpy.ops.mesh.primitive_cone_add(vertices=vertices)
            elif primitive=="plane": bpy.ops.mesh.primitive_plane_add()
            else: raise ValueError("primitive_not_supported")
            bpy.context.object.name=target
        elif kind=="create_armature":
            bpy.ops.object.armature_add(); arm=bpy.context.object; arm.name=target
            # Blender seeds new rigs with a generic Bone. Remove it so every
            # bone in the candidate is attributable to an explicit plan item.
            bpy.context.view_layer.objects.active=arm
            bpy.ops.object.mode_set(mode="EDIT")
            for bone in list(arm.data.edit_bones): arm.data.edit_bones.remove(bone)
            bpy.ops.object.mode_set(mode="OBJECT")
        elif kind=="create_bone":
            arm=bpy.data.objects[target]
            if arm.type!="ARMATURE": raise ValueError("bone_target_not_armature")
            bpy.context.view_layer.objects.active=arm
            bpy.ops.object.mode_set(mode="EDIT")
            bone=arm.data.edit_bones.new(op_id)
            bone.head=args.get("head",[0,0,0]); bone.tail=args.get("tail",[0,1,0])
            parent_name=args.get("parent")
            if parent_name is not None:
                parent=arm.data.edit_bones.get(parent_name)
                if parent is None: raise ValueError("bone_parent_missing")
                bone.parent=parent
            bpy.ops.object.mode_set(mode="OBJECT")
        elif kind=="set_transform":
            obj=bpy.data.objects[target]
            for key in ("location","rotation","scale"):
                if key in args: setattr(obj,"rotation_euler" if key=="rotation" else key,args[key])
        elif kind=="bind_armature":
            obj=bpy.data.objects[target]; arm=bpy.data.objects[args["armature"]]
            if obj.type!="MESH" or arm.type!="ARMATURE": raise ValueError("armature_binding_type_invalid")
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True); arm.select_set(True); bpy.context.view_layer.objects.active=arm
            bpy.ops.object.parent_set(type="ARMATURE_AUTO")
            if not any(mod.type=="ARMATURE" and mod.object==arm for mod in obj.modifiers):
                raise ValueError("armature_binding_modifier_missing")
            bone_names={bone.name for bone in arm.data.bones}
            if not bone_names.intersection(group.name for group in obj.vertex_groups):
                raise ValueError("armature_binding_weights_missing")
        else: raise ValueError("operation_not_yet_supported_by_blender_driver:"+kind)
        results.append({"operation_id":op_id,"status":"applied"})
    if output_path.lower().endswith(".blend"):
        bpy.ops.wm.save_as_mainfile(filepath=output_path)
    elif output_path.lower().endswith(".glb"):
        # Omit generated normals and UVs because the static authoring operations
        # do not author those channels. This also preserves source vertex counts
        # across GLB round-trip inspection instead of counting split loop vertices.
        bpy.ops.export_scene.gltf(filepath=output_path, export_format="GLB", export_apply=True,
                                  export_normals=False, export_texcoords=False)
    else:
        raise ValueError("output_format_unsupported")
    print("SENTIENTOS_AVATAR_RESULT="+json.dumps({"status":"completed","operations":results},sort_keys=True))
if __name__=="__main__": main(sys.argv)
