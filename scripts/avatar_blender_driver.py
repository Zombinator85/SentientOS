# mypy: disable-error-code="no-untyped-def,no-untyped-call,import-not-found"
"""Repository-owned Blender driver.  JSON plans contain no executable code."""
from __future__ import annotations
import hashlib, json, sys

def _digest(value): return "sha256:"+hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def translate(plan):
    allowed={"create_primitive_mesh","duplicate_object","rename_object","set_transform","assign_material","create_armature","create_bone","parent_object","bind_armature","create_shape_key","register_channel","set_label"}
    if plan.get("schema_version")!="sentientos.avatar_authoring_plan:v1" or any(op.get("kind") not in allowed for op in plan.get("operations",[])): raise ValueError("invalid_plan")
    return tuple((op["operation_id"],op["kind"],op["target"],dict(op["arguments"])) for op in plan["operations"])
def main(argv):
    plan_path,output_path,claimed=argv[-3:]; plan=json.load(open(plan_path,encoding="utf-8")); embedded=plan.pop("plan_digest",None)
    if embedded!=claimed or _digest(plan)!=claimed: raise ValueError("plan_digest_mismatch")
    operations=translate(plan)
    import bpy  # imported only inside Blender
    results=[]
    for op_id,kind,target,args in operations:
        # The initial real driver deliberately supports only inspectable rigging primitives.
        if kind=="create_armature": bpy.ops.object.armature_add(); bpy.context.object.name=target
        elif kind=="create_bone":
            arm=bpy.data.objects[target]; bpy.context.view_layer.objects.active=arm; bpy.ops.object.mode_set(mode="EDIT"); bone=arm.data.edit_bones.new(args.get("bone",op_id)); bone.head=args.get("head",[0,0,0]); bone.tail=args.get("tail",[0,1,0]); bone.parent=arm.data.edit_bones.get(args.get("parent")); bpy.ops.object.mode_set(mode="OBJECT")
        elif kind=="set_transform":
            obj=bpy.data.objects[target]
            for key in ("location","rotation","scale"):
                if key in args: setattr(obj,"rotation_euler" if key=="rotation" else key,args[key])
        else: raise ValueError("operation_not_yet_supported_by_blender_driver:"+kind)
        results.append({"operation_id":op_id,"status":"applied"})
    bpy.ops.wm.save_as_mainfile(filepath=output_path); print("SENTIENTOS_AVATAR_RESULT="+json.dumps({"status":"completed","operations":results},sort_keys=True))
if __name__=="__main__": main(sys.argv)
