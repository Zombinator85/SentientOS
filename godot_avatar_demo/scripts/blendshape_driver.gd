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
@export var mouth_shape := "MouthOpen"
@export var viseme_to_shape_weight := {
    "a": 0.9,
    "e": 0.8,
    "i": 0.7,
    "o": 0.8,
    "u": 0.7,
    "default": 0.75,
}
@export var viseme_floor := 0.0

var _active_shapes: Array[int] = []
var _viseme_tween: Tween


func apply_expression(expression: String, mood: String, intensity: float) -> void:
    var mesh: MeshInstance3D = _resolve_mesh()
    if mesh == null:
        return

    var target: Variant = expression_to_shape.get(expression, mood_to_shape.get(mood, null))
    if target == null:
        return

    var shape_name: String = str(target)
    var shape_index: int = _blend_shape_index(mesh, shape_name)
    if shape_index < 0:
        return
    _reset(mesh)
    var weight: float = clampf(intensity * intensity_multiplier, 0.0, 1.0)
    mesh.set_blend_shape_value(shape_index, weight)
    _active_shapes = [shape_index]


func play_viseme_timeline(timeline: Array, anchor_timestamp: float = 0.0) -> void:
    var mesh: MeshInstance3D = _resolve_mesh()
    if mesh == null or mouth_shape == "":
        return

    if _viseme_tween:
        _viseme_tween.kill()
    _reset_viseme(mesh)
    _viseme_tween = get_tree().create_tween()

    var elapsed: float = 0.0
    if anchor_timestamp > 0.0:
        elapsed = maxf(0.0, Time.get_unix_time_from_system() - float(anchor_timestamp))

    for cue in timeline:
        if typeof(cue) != TYPE_DICTIONARY:
            continue

        var start: float = float(cue.get("time", 0.0)) - elapsed
        var duration: float = float(cue.get("duration", 0.05))
        var viseme: String = str(cue.get("viseme", cue.get("value", "neutral"))).to_lower()
        var weight: float = float(viseme_to_shape_weight.get(viseme, viseme_to_shape_weight.get("default", 0.75)))
        weight = clampf(weight, viseme_floor, 1.0)
        start = maxf(start, 0.0)
        duration = maxf(duration, 0.05)

        _viseme_tween.tween_callback(_set_blend_shape_by_name.bind(mesh, mouth_shape, weight)).set_delay(start)
        _viseme_tween.tween_callback(_set_blend_shape_by_name.bind(mesh, mouth_shape, 0.0)).set_delay(start + duration)


func _resolve_mesh() -> MeshInstance3D:
    if mesh_path == NodePath(""):
        return null
    return get_node_or_null(mesh_path) as MeshInstance3D


func _blend_shape_index(mesh: MeshInstance3D, shape_name: String) -> int:
    if mesh.mesh == null:
        return -1
    return mesh.mesh.find_blend_shape_by_name(shape_name)


func _set_blend_shape_by_name(mesh: MeshInstance3D, shape_name: String, weight: float) -> void:
    var shape_index: int = _blend_shape_index(mesh, shape_name)
    if shape_index >= 0:
        mesh.set_blend_shape_value(shape_index, weight)


func _reset(mesh: MeshInstance3D) -> void:
    if not mesh or _active_shapes.is_empty():
        return
    _reset_viseme(mesh)
    for shape in _active_shapes:
        mesh.set_blend_shape_value(shape, 0.0)
    _active_shapes.clear()


func _reset_viseme(mesh: MeshInstance3D) -> void:
    if not mesh or mouth_shape == "":
        return
    _set_blend_shape_by_name(mesh, mouth_shape, 0.0)
