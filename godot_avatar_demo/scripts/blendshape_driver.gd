extends Node

@export var mesh_path: NodePath
@export var expression_to_shape := {
    "smile": "FaceSmile",
    "frown": "FaceFrown",
    "rest": "FaceNeutral",
}
@export var mood_to_shape := {
    "joy": "FaceSmile",
    "calm": "FaceNeutral",
    "anger": "FaceFrown",
}
@export var intensity_multiplier := 1.0

var _active_shapes: Array[StringName] = []


func apply_expression(expression: String, mood: String, intensity: float) -> void:
    var mesh := _resolve_mesh()
    if mesh == null:
        return

    var target := expression_to_shape.get(expression, mood_to_shape.get(mood, null))
    if target == null:
        return

    _reset(mesh)
    var weight := clamp(intensity * intensity_multiplier, 0.0, 1.0)
    if mesh.has_method("set_blend_shape_value"):
        mesh.set_blend_shape_value(target, weight)
        _active_shapes = [target]


func _resolve_mesh():
    if mesh_path == NodePath(""):
        return null
    return get_node_or_null(mesh_path)


func _reset(mesh):
    if not mesh or _active_shapes.is_empty():
        return
    for shape in _active_shapes:
        if mesh.has_method("set_blend_shape_value"):
            mesh.set_blend_shape_value(shape, 0.0)
    _active_shapes.clear()
