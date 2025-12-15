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

var _active_shapes: Array[StringName] = []
var _viseme_tween: Tween


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


func play_viseme_timeline(timeline: Array, anchor_timestamp: float = 0.0) -> void:
    var mesh := _resolve_mesh()
    if mesh == null or mouth_shape == "":
        return

    if _viseme_tween:
        _viseme_tween.kill()
    _reset_viseme(mesh)
    _viseme_tween = get_tree().create_tween()

    var elapsed := 0.0
    if anchor_timestamp > 0.0:
        elapsed = max(0.0, Time.get_unix_time_from_system() - float(anchor_timestamp))

    for cue in timeline:
        if typeof(cue) != TYPE_DICTIONARY:
            continue

        var start := float(cue.get("time", 0.0)) - elapsed
        var duration := float(cue.get("duration", 0.05))
        var viseme := str(cue.get("viseme", cue.get("value", "neutral"))).to_lower()
        var weight := float(viseme_to_shape_weight.get(viseme, viseme_to_shape_weight.get("default", 0.75)))
        weight = clamp(weight, viseme_floor, 1.0)
        start = max(start, 0.0)
        duration = max(duration, 0.05)

        _viseme_tween.tween_callback(Callable(mesh, "set_blend_shape_value").bind(mouth_shape, weight)).set_delay(start)
        _viseme_tween.tween_callback(Callable(mesh, "set_blend_shape_value").bind(mouth_shape, 0.0)).set_delay(start + duration)


func _resolve_mesh():
    if mesh_path == NodePath(""):
        return null
    return get_node_or_null(mesh_path)


func _reset(mesh):
    if not mesh or _active_shapes.is_empty():
        return
    _reset_viseme(mesh)
    for shape in _active_shapes:
        if mesh.has_method("set_blend_shape_value"):
            mesh.set_blend_shape_value(shape, 0.0)
    _active_shapes.clear()


func _reset_viseme(mesh):
    if not mesh or mouth_shape == "":
        return
    if mesh.has_method("set_blend_shape_value"):
        mesh.set_blend_shape_value(mouth_shape, 0.0)
