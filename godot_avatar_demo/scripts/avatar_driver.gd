extends Node

@export var listen_port := 18188
@export var auto_listen := true
@export var blendshape_driver_path: NodePath
@export var motion_driver_path: NodePath
@export var status_label_path: NodePath

var _server := UDPServer.new()
var _last_packet := {}
const NORMAL_RENDER_FPS := 60
const GAMING_RENDER_FPS := 15


func _ready() -> void:
	_set_workload_mode("normal")
	if auto_listen:
		var result := _server.listen(listen_port)
		if result == OK:
			_write_status("Listening on UDP %d" % listen_port)
		else:
			_write_status("UDP listener unavailable (%s)" % error_string(result))
	else:
		_write_status("Preview mode")


func _process(_delta: float) -> void:
	if not _server.is_listening():
		return

	_server.poll()
	while _server.is_connection_available():
		var peer := _server.take_connection()
		_drain_peer(peer)


func _drain_peer(peer: PacketPeerUDP) -> void:
	while peer.get_available_packet_count() > 0:
		var packet := peer.get_packet().get_string_from_utf8()
		var payload: Variant = JSON.parse_string(packet)
		if typeof(payload) == TYPE_DICTIONARY:
			_apply_state(payload as Dictionary)


func _apply_state(state: Dictionary) -> void:
	_last_packet = state
	var workload_mode: String = str(state.get("workload_mode", "normal"))
	if workload_mode != "gaming":
		workload_mode = "normal"
	_set_workload_mode(workload_mode)
	var expression: String = str(state.get("expression", "rest"))
	var mood: String = str(state.get("mood", "calm"))
	var intensity := float(state.get("intensity", 0.0))
	var motion: String = str(state.get("motion", "idle"))
	var phrase_value: Variant = state.get("phrase", {})
	var phrase_block: Dictionary = phrase_value if phrase_value is Dictionary else {}
	var phrase: String = str(phrase_block.get("text", state.get("current_phrase", "")))
	var muted := bool(phrase_block.get("muted", false))
	var status: String = "%s @ %.2f (%s) [%s workload, %d FPS cap]" % [
		expression, intensity, motion, workload_mode, Engine.max_fps
	]
	if phrase != "":
		status += " – %s%s" % ["(muted) " if muted else "", phrase]
	_write_status(status)

	var blendshape_driver: Node = _resolve_node(blendshape_driver_path)
	if blendshape_driver and blendshape_driver.has_method("apply_expression"):
		blendshape_driver.apply_expression(expression, mood, intensity)
		var viseme_value: Variant = state.get("viseme_timeline", [])
		var visemes: Array = viseme_value if viseme_value is Array else []
		if visemes is Array and blendshape_driver.has_method("play_viseme_timeline"):
			blendshape_driver.play_viseme_timeline(visemes, float(state.get("timestamp", 0.0)))

	var motion_driver: Node = _resolve_node(motion_driver_path)
	if motion_driver and motion_driver.has_method("apply_motion"):
		motion_driver.apply_motion(motion)


func _set_workload_mode(workload_mode: String) -> void:
	# This caps only the companion renderer process. It does not change host or
	# game scheduling and does not claim to reserve system resources.
	Engine.max_fps = GAMING_RENDER_FPS if workload_mode == "gaming" else NORMAL_RENDER_FPS


func _write_status(message: String) -> void:
	var label: Label = _resolve_label(status_label_path)
	if label and label.has_method("set_text"):
		label.text = message


func _resolve_node(path: NodePath) -> Node:
	if path == NodePath(""):
		return null
	return get_node_or_null(path)


func _resolve_label(path: NodePath) -> Label:
	if path == NodePath(""):
		return null
	return get_node_or_null(path) as Label
