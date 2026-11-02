extends Node

@export var mesh_path: NodePath
@export var mouth_node_path: NodePath
@export var eye_left_path: NodePath
@export var eye_right_path: NodePath
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
var _mouth_rest := Vector3.ONE
var _eye_left_rest := Vector3.ONE
var _eye_right_rest := Vector3.ONE
var _last_apply_report := {"status": "not_applied"}


func _ready() -> void:
	var mouth := _resolve_node(mouth_node_path)
	var left_eye := _resolve_node(eye_left_path)
	var right_eye := _resolve_node(eye_right_path)
	if mouth:
		_mouth_rest = mouth.scale
	if left_eye:
		_eye_left_rest = left_eye.scale
	if right_eye:
		_eye_right_rest = right_eye.scale


func apply_expression(expression: String, mood: String, intensity: float) -> Dictionary:
	var mesh: MeshInstance3D = _resolve_mesh()
	if mesh == null:
		_last_apply_report = {"status": "unavailable", "reason": "mesh_unavailable"}
		return _last_apply_report.duplicate(true)

	var target: Variant = expression_to_shape.get(expression, mood_to_shape.get(mood, null))
	if target == null:
		_last_apply_report = {"status": "unsupported", "reason": "expression_mapping_unavailable"}
		return _last_apply_report.duplicate(true)

	var shape_name: String = str(target)
	var shape_index: int = _blend_shape_index(mesh, shape_name)
	_reset(mesh)
	var weight: float = clampf(intensity * intensity_multiplier, 0.0, 1.0)
	if shape_index >= 0:
		mesh.set_blend_shape_value(shape_index, weight)
		_active_shapes = [shape_index]
		_last_apply_report = {"status": "blend_shape_applied", "shape": shape_name,
			"weight": mesh.get_blend_shape_value(shape_index)}
	else:
		_apply_procedural_expression(expression, mood, weight)
		var mouth := _resolve_node(mouth_node_path)
		var left_eye := _resolve_node(eye_left_path)
		var right_eye := _resolve_node(eye_right_path)
		_last_apply_report = {"status": "procedural_fallback_applied", "target": shape_name,
			"weight": weight, "mouth_scale": _vector3_payload(mouth.scale) if mouth else null,
			"left_eye_scale": _vector3_payload(left_eye.scale) if left_eye else null,
			"right_eye_scale": _vector3_payload(right_eye.scale) if right_eye else null}
	return _last_apply_report.duplicate(true)


func latest_apply_report() -> Dictionary:
	return _last_apply_report.duplicate(true)


func _vector3_payload(value: Vector3) -> Dictionary:
	return {"x": value.x, "y": value.y, "z": value.z}


func play_viseme_timeline(timeline: Array, anchor_timestamp: float = 0.0) -> void:
	var mesh: MeshInstance3D = _resolve_mesh()
	if mesh == null or mouth_shape == "":
		return

	if _viseme_tween:
		_viseme_tween.kill()
	_reset_viseme(mesh)
	if timeline.is_empty():
		return
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


func _resolve_node(path: NodePath) -> Node3D:
	if path == NodePath(""):
		return null
	return get_node_or_null(path) as Node3D


func _blend_shape_index(mesh: MeshInstance3D, shape_name: String) -> int:
	if mesh.mesh == null or not mesh.mesh is ArrayMesh:
		return -1
	var array_mesh := mesh.mesh as ArrayMesh
	if array_mesh.get_blend_shape_count() == 0:
		return -1
	return array_mesh.find_blend_shape_by_name(shape_name)


func _set_blend_shape_by_name(mesh: MeshInstance3D, shape_name: String, weight: float) -> void:
	var shape_index: int = _blend_shape_index(mesh, shape_name)
	if shape_index >= 0:
		mesh.set_blend_shape_value(shape_index, weight)
	else:
		_set_procedural_mouth_open(weight)


func _reset(mesh: MeshInstance3D) -> void:
	if not mesh or _active_shapes.is_empty():
		return
	_reset_viseme(mesh)
	for shape in _active_shapes:
		mesh.set_blend_shape_value(shape, 0.0)
	_active_shapes.clear()


func _reset_viseme(mesh: MeshInstance3D) -> void:
	if not mesh or mouth_shape == "":
		_set_procedural_mouth_open(0.0)
		return
	if _blend_shape_index(mesh, mouth_shape) >= 0:
		_set_blend_shape_by_name(mesh, mouth_shape, 0.0)
	else:
		_set_procedural_mouth_open(0.0)


func _apply_procedural_expression(expression: String, mood: String, intensity: float) -> void:
	var mouth := _resolve_node(mouth_node_path)
	var left_eye := _resolve_node(eye_left_path)
	var right_eye := _resolve_node(eye_right_path)
	var label := expression if expression in ["smile", "frown", "rest"] else mood
	var mouth_factor := 1.0
	var eye_factor := 1.0
	match label:
		"smile", "joy":
			mouth_factor = 1.9
			eye_factor = 0.86
		"frown", "anger":
			mouth_factor = 0.58
			eye_factor = 0.82
	if mouth:
		mouth.scale = Vector3(_mouth_rest.x, lerpf(_mouth_rest.y, _mouth_rest.y * mouth_factor, intensity), _mouth_rest.z)
	if left_eye:
		left_eye.scale = Vector3(_eye_left_rest.x, _eye_left_rest.y * lerpf(1.0, eye_factor, intensity), _eye_left_rest.z)
	if right_eye:
		right_eye.scale = Vector3(_eye_right_rest.x, _eye_right_rest.y * lerpf(1.0, eye_factor, intensity), _eye_right_rest.z)


func _set_procedural_mouth_open(weight: float) -> void:
	var mouth := _resolve_node(mouth_node_path)
	if mouth:
		mouth.scale = Vector3(_mouth_rest.x, _mouth_rest.y * lerpf(1.0, 2.4, clampf(weight, 0.0, 1.0)), _mouth_rest.z)
