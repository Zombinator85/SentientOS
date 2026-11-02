# mypy: disable-error-code="import-not-found,var-annotated"
"""Static bounded structural inspector executed only by configured Blender."""
from __future__ import annotations
import json
import sys
import bpy

def main() -> None:
    try:
        separator=sys.argv.index("--")
        artifact_path,asset_format=sys.argv[separator+1:]
    except (ValueError,TypeError):
        raise ValueError("inspector_arguments_invalid") from None
    if asset_format=="glb":
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=artifact_path)
    elif asset_format!="blend":
        raise ValueError("asset_format_unsupported")
    objects={}; armatures={}; bones={}; shape_keys={}; shape_key_geometry={}; materials={}
    for material in bpy.data.materials:
        settings: dict[str, object]={"base_color":list(material.diffuse_color),"metallic":None,"roughness":None}
        if material.use_nodes and material.node_tree:
            shader=next((node for node in material.node_tree.nodes if node.type=="BSDF_PRINCIPLED"),None)
            if shader:
                metallic_input=shader.inputs.get("Metallic")
                roughness_input=shader.inputs.get("Roughness")
                if metallic_input: settings["metallic"]=float(metallic_input.default_value)
                if roughness_input: settings["roughness"]=float(roughness_input.default_value)
        materials[material.name]=settings
    # Blender's glTF importer creates temporary custom-shape helpers in this
    # explicitly non-exported collection for imported armatures. They are not
    # nodes in the GLB and must not become candidate structure.
    imported_helpers=({obj for collection in bpy.data.collections
                       if collection.name=="glTF_not_exported" for obj in collection.objects}
                      if asset_format=="glb" else set())
    for obj in sorted((item for item in bpy.data.objects if item not in imported_helpers),key=lambda item:item.name):
        objects[obj.name]={"type":obj.type,"vertex_count":len(obj.data.vertices) if obj.type=="MESH" else None,"transform":{"location":list(obj.location),"rotation":list(obj.rotation_euler),"scale":list(obj.scale)},"materials":[slot.material.name for slot in obj.material_slots if slot.material],"parent":obj.parent.name if obj.parent else None,"armature":next((m.object.name for m in obj.modifiers if m.type=="ARMATURE" and m.object),None),"vertex_group_names":sorted(group.name for group in obj.vertex_groups)}
        if obj.type=="ARMATURE":
            armatures[obj.name]={"bones":{}}
            for bone in sorted(obj.data.bones,key=lambda item:item.name):
                data={"parent":bone.parent.name if bone.parent else None,"head":list(bone.head_local),"tail":list(bone.tail_local)}; armatures[obj.name]["bones"][bone.name]=data; bones[f"{obj.name}/{bone.name}"]=data
        keys=getattr(getattr(obj,"data",None),"shape_keys",None)
        if keys:
            shape_keys[obj.name]=[key.name for key in keys.key_blocks]
            basis=keys.reference_key
            shape_key_geometry[obj.name]={}
            if basis:
                for key in keys.key_blocks:
                    if key==basis: continue
                    deltas=[(vertex.co-basis.data[index].co).length for index,vertex in enumerate(key.data)]
                    shape_key_geometry[obj.name][key.name]={
                        "changed_vertex_count":sum(1 for delta in deltas if delta>1e-6),
                        "maximum_vertex_delta":max(deltas,default=0.0)}
    value={"body_id":None,"labels":{},"objects":objects,"armatures":armatures,"bones":bones,"materials":materials,"shape_keys":shape_keys,"shape_key_geometry":shape_key_geometry,"channels":{},"warnings":[],"unsupported":[]}
    print("SENTIENTOS_AVATAR_INSPECTION="+json.dumps(value,sort_keys=True,separators=(",",":")))
if __name__=="__main__": main()
