# mypy: disable-error-code="no-untyped-def,no-untyped-call,import-not-found"
"""Repository-owned Blender driver.  JSON plans contain no executable code."""
from __future__ import annotations
import hashlib, json, math, sys

SUPPORTED_OPERATIONS={"create_primitive_mesh","create_armature","create_bone","set_transform","bind_armature","create_material","assign_material","create_shape_key"}
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
def validate_material_bounds(plan):
    for operation in plan.get("operations",[]):
        if operation.get("kind")!="create_material": continue
        arguments=operation.get("arguments",{})
        if not isinstance(arguments,dict) or set(arguments)!={"base_color","metallic","roughness"}:
            raise ValueError("material_arguments_invalid")
        color=arguments["base_color"]
        if (not isinstance(color,list) or len(color)!=4
                or any(type(value) not in (int,float) or not math.isfinite(float(value))
                       or not 0.0<=float(value)<=1.0 for value in color)):
            raise ValueError("material_color_invalid")
        for key in ("metallic","roughness"):
            value=arguments[key]
            if type(value) not in (int,float) or not math.isfinite(float(value)) or not 0.0<=float(value)<=1.0:
                raise ValueError("material_property_invalid")
def validate_shape_key_bounds(plan):
    for operation in plan.get("operations",[]):
        if operation.get("kind")!="create_shape_key": continue
        arguments=operation.get("arguments",{})
        if (not isinstance(arguments,dict) or set(arguments)!={"shape_key","vertex_offsets"}
                or not isinstance(arguments["shape_key"],str) or not arguments["shape_key"]
                or len(arguments["shape_key"])>128 or any(c in arguments["shape_key"] for c in ("/","\\","\x00"))):
            raise ValueError("shape_key_arguments_invalid")
        offsets=arguments["vertex_offsets"]
        if not isinstance(offsets,list) or not 1<=len(offsets)<=256:
            raise ValueError("shape_key_vertex_offsets_invalid")
        seen=set()
        for item in offsets:
            if (not isinstance(item,dict) or set(item)!={"vertex_index","offset"}
                    or type(item["vertex_index"]) is not int
                    or not 0<=item["vertex_index"]<MAX_PRIMITIVE_MESH_VERTICES
                    or item["vertex_index"] in seen):
                raise ValueError("shape_key_vertex_offsets_invalid")
            seen.add(item["vertex_index"])
            vector=item["offset"]
            if (not isinstance(vector,list) or len(vector)!=3
                    or any(type(value) not in (int,float) or not math.isfinite(float(value))
                           or abs(float(value))>0.25 for value in vector)
                    or not any(float(value)!=0.0 for value in vector)):
                raise ValueError("shape_key_vertex_offset_bound_exceeded")
def translate(plan):
    allowed=SUPPORTED_OPERATIONS
    if plan.get("schema_version")!="sentientos.avatar_authoring_plan:v1" or any(op.get("kind") not in allowed for op in plan.get("operations",[])): raise ValueError("invalid_plan")
    validate_geometry_bounds(plan)
    validate_material_bounds(plan)
    validate_shape_key_bounds(plan)
    if any(not isinstance(op.get("arguments"),dict) for op in plan.get("operations",[])):
        raise ValueError("authoring_operation_arguments_invalid")
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
        elif kind=="create_material":
            if bpy.data.materials.get(target) is not None: raise ValueError("material_already_exists")
            material=bpy.data.materials.new(target)
            color=[float(value) for value in args["base_color"]]
            material.diffuse_color=color
            material.use_nodes=True
            shader=next((node for node in material.node_tree.nodes if node.type=="BSDF_PRINCIPLED"),None)
            if shader is None: raise ValueError("principled_shader_unavailable")
            shader.inputs["Base Color"].default_value=color
            shader.inputs["Metallic"].default_value=float(args["metallic"])
            shader.inputs["Roughness"].default_value=float(args["roughness"])
        elif kind=="assign_material":
            obj=bpy.data.objects.get(target)
            material=bpy.data.materials.get(args["material"])
            if obj is None or obj.type!="MESH" or material is None:
                raise ValueError("material_assignment_target_invalid")
            obj.data.materials.append(material)
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
        elif kind=="create_shape_key":
            obj=bpy.data.objects.get(target)
            if obj is None or obj.type!="MESH": raise ValueError("shape_key_target_not_mesh")
            if obj.data.shape_keys is not None and obj.data.shape_keys.key_blocks.get(args["shape_key"]) is not None:
                raise ValueError("shape_key_already_exists")
            if obj.data.shape_keys is None: obj.shape_key_add(name="Basis",from_mix=False)
            shape=obj.shape_key_add(name=args["shape_key"],from_mix=False)
            from mathutils import Vector
            for item in args["vertex_offsets"]:
                index=item["vertex_index"]
                if index>=len(shape.data): raise ValueError("shape_key_vertex_index_out_of_range")
                shape.data[index].co += Vector(item["offset"])
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
