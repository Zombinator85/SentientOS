# mypy: disable-error-code="import-not-found,var-annotated"
"""Static bounded structural inspector executed only by configured Blender."""
from __future__ import annotations
import json
import bpy

def main() -> None:
    objects={}; armatures={}; bones={}; shape_keys={}; materials={m.name:{} for m in bpy.data.materials}
    for obj in sorted(bpy.data.objects,key=lambda item:item.name):
        objects[obj.name]={"type":obj.type,"transform":{"location":list(obj.location),"rotation":list(obj.rotation_euler),"scale":list(obj.scale)},"materials":[slot.material.name for slot in obj.material_slots if slot.material],"parent":obj.parent.name if obj.parent else None,"armature":next((m.object.name for m in obj.modifiers if m.type=="ARMATURE" and m.object),None)}
        if obj.type=="ARMATURE":
            armatures[obj.name]={"bones":{}}
            for bone in sorted(obj.data.bones,key=lambda item:item.name):
                data={"parent":bone.parent.name if bone.parent else None,"head":list(bone.head_local),"tail":list(bone.tail_local)}; armatures[obj.name]["bones"][bone.name]=data; bones[f"{obj.name}/{bone.name}"]=data
        keys=getattr(getattr(obj,"data",None),"shape_keys",None)
        if keys: shape_keys[obj.name]=[key.name for key in keys.key_blocks]
    value={"body_id":None,"labels":{},"objects":objects,"armatures":armatures,"bones":bones,"materials":materials,"shape_keys":shape_keys,"channels":{},"warnings":[],"unsupported":[]}
    print("SENTIENTOS_AVATAR_INSPECTION="+json.dumps(value,sort_keys=True,separators=(",",":")))
if __name__=="__main__": main()
