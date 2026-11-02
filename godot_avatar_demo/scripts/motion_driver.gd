extends Node

@export var animation_player_path: NodePath
@export var head_pivot_path: NodePath
@export var left_arm_path: NodePath
@export var body_path: NodePath
@export var default_motion := "idle"
@export var supported_motions := ["idle", "wave", "nod"]

var _active_motion := ""
var _motion_time := 0.0
var _elapsed := 0.0
var _head_rest := Vector3.ZERO
var _arm_rest := Vector3.ZERO
var _body_rest := Vector3.ZERO


func _ready() -> void:
	var head := _resolve_node(head_pivot_path)
	var arm := _resolve_node(left_arm_path)
	var body := _resolve_node(body_path)
	if head:
		_head_rest = head.rotation
	if arm:
		_arm_rest = arm.rotation
	if body:
		_body_rest = body.position
	apply_motion(default_motion)


func _process(delta: float) -> void:
	var player: AnimationPlayer = _resolve_player()
	if player and player.is_playing():
		return
	_elapsed += delta
	var body := _resolve_node(body_path)
	if body:
		body.position.y = _body_rest.y + sin(_elapsed * 2.0) * 0.025

	var head := _resolve_node(head_pivot_path)
	var arm := _resolve_node(left_arm_path)
	if _active_motion == "wave":
		_motion_time += delta
		if arm:
			arm.rotation.z = _arm_rest.z - 0.15 + sin(_motion_time * 12.0) * 0.72
		if _motion_time >= 1.35:
			_finish_gesture()
	elif _active_motion == "nod":
		_motion_time += delta
		if head:
			head.rotation.x = _head_rest.x + sin(_motion_time * 11.0) * 0.24
		if _motion_time >= 0.85:
			_finish_gesture()
	else:
		if head:
			head.rotation.y = _head_rest.y + sin(_elapsed * 0.7) * 0.035
		if arm:
			arm.rotation.z = lerp_angle(arm.rotation.z, _arm_rest.z, clampf(delta * 8.0, 0.0, 1.0))


func apply_motion(motion: String) -> void:
	var target := motion if motion in supported_motions else default_motion
	if target == _active_motion:
		return
	if _active_motion != "idle":
		_finish_gesture()

	var player: AnimationPlayer = _resolve_player()
	if player and player.has_animation(target):
		var animation := player.get_animation(target)
		if animation and animation.length > 0.0 and animation.get_track_count() > 0:
			player.play(target)
			_active_motion = target
			return

	if player and player.is_playing():
		player.stop()
	_active_motion = target
	_motion_time = 0.0
	if target == "idle":
		var head := _resolve_node(head_pivot_path)
		if head:
			head.rotation.x = _head_rest.x
		return
	if target == "wave":
		var arm := _resolve_node(left_arm_path)
		if arm:
			arm.rotation.z = _arm_rest.z - 0.15
	elif target == "nod":
		var head := _resolve_node(head_pivot_path)
		if head:
			head.rotation.y = _head_rest.y


func renderer_report() -> Dictionary:
	var player := _resolve_player()
	var head := _resolve_node(head_pivot_path)
	var arm := _resolve_node(left_arm_path)
	var body := _resolve_node(body_path)
	return {
		"active_motion": _active_motion,
		"animation_player_active": player != null and player.is_playing(),
		"head_rotation_radians": _vector3_payload(head.rotation) if head else null,
		"left_arm_rotation_radians": _vector3_payload(arm.rotation) if arm else null,
		"body_position": _vector3_payload(body.position) if body else null,
		"observed_nodes": {"head": head != null, "left_arm": arm != null, "body": body != null},
	}


func _vector3_payload(value: Vector3) -> Dictionary:
	return {"x": value.x, "y": value.y, "z": value.z}


func _finish_gesture() -> void:
	var head := _resolve_node(head_pivot_path)
	var arm := _resolve_node(left_arm_path)
	if head:
		head.rotation.x = _head_rest.x
		if _active_motion == "nod":
			head.rotation.y = _head_rest.y
	if arm:
		arm.rotation.z = _arm_rest.z
	_active_motion = "idle"
	_motion_time = 0.0


func _resolve_player() -> AnimationPlayer:
	if animation_player_path == NodePath(""):
		return null
	return get_node_or_null(animation_player_path) as AnimationPlayer


func _resolve_node(path: NodePath) -> Node3D:
	if path == NodePath(""):
		return null
	return get_node_or_null(path) as Node3D
