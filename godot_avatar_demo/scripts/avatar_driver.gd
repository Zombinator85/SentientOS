extends Node

@export var listen_port := 18188
@export var auto_listen := true
@export var blendshape_driver_path: NodePath
@export var motion_driver_path: NodePath
@export var candidate_body_adapter_path: NodePath
@export var status_label_path: NodePath
@export var renderer_report_relay_port := 0

var _server := UDPServer.new()
var _last_packet := {}
var _renderer_generation_id := ""
var _report_sequence := 0
var _last_renderer_report := {}
var _candidate_report_sequence := 0
var _last_candidate_renderer_report := {}
var _renderer_report_sender: PacketPeerUDP
const NORMAL_RENDER_FPS := 60
const GAMING_RENDER_FPS := 15
const LOOPBACK_BIND_ADDRESS := "127.0.0.1"


func _ready() -> void:
	_renderer_generation_id = OS.get_environment("SENTIENTOS_RENDERER_GENERATION_ID")
	if not _is_generation_id(_renderer_generation_id):
		_renderer_generation_id = "godot-demo-" + str(Time.get_ticks_usec())
	var relay_port_text := OS.get_environment("SENTIENTOS_RENDERER_REPORT_RELAY_PORT")
	if not relay_port_text.is_empty():
		if not relay_port_text.is_valid_int():
			_write_status("Renderer report relay port invalid")
		else:
			renderer_report_relay_port = relay_port_text.to_int()
	if renderer_report_relay_port < 0 or renderer_report_relay_port > 65535:
		renderer_report_relay_port = 0
		_write_status("Renderer report relay port out of range")
	if renderer_report_relay_port > 0:
		_renderer_report_sender = PacketPeerUDP.new()
		var sender_error := _renderer_report_sender.connect_to_host(
			LOOPBACK_BIND_ADDRESS, renderer_report_relay_port)
		if sender_error != OK:
			_renderer_report_sender = null
			_write_status("Renderer report relay unavailable (%s)" % error_string(sender_error))
	_set_workload_mode("normal")
	if auto_listen:
		var result := _server.listen(listen_port, LOOPBACK_BIND_ADDRESS)
		if result == OK:
			_write_status("Listening on loopback UDP %d" % listen_port)
		else:
			_write_status("UDP listener unavailable (%s)" % error_string(result))
	else:
		_write_status("Preview mode")


func _process(delta: float) -> void:
	if not _server.is_listening():
		return

	_server.poll()
	while _server.is_connection_available():
		var peer := _server.take_connection()
		_drain_peer(peer, delta)


func _drain_peer(peer: PacketPeerUDP, frame_delta_seconds: float) -> void:
	while peer.get_available_packet_count() > 0:
		var packet := peer.get_packet().get_string_from_utf8()
		var payload: Variant = JSON.parse_string(packet)
		if typeof(payload) == TYPE_DICTIONARY:
			_apply_state(payload as Dictionary, frame_delta_seconds)


func _apply_state(state: Dictionary, frame_delta_seconds: float = -1.0) -> void:
	var apply_started_usec := Time.get_ticks_usec()
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
	var metadata_value: Variant = state.get("metadata", {})
	var command_metadata: Dictionary = metadata_value if metadata_value is Dictionary else {}
	var phrase: String = str(phrase_block.get("text", state.get("current_phrase", "")))
	var muted := bool(phrase_block.get("muted", false))
	var status: String = "%s @ %.2f (%s) [%s workload, %d FPS cap]" % [
		expression, intensity, motion, workload_mode, Engine.max_fps
	]
	if phrase != "":
		status += " – %s%s" % ["(muted) " if muted else "", phrase]
	_write_status(status)

	var blendshape_driver: Node = _resolve_node(blendshape_driver_path)
	var expression_report := {"status": "unavailable", "reason": "blendshape_driver_unavailable"}
	var viseme_value: Variant = state.get("viseme_timeline", [])
	var visemes: Array = viseme_value if viseme_value is Array else []
	if blendshape_driver and blendshape_driver.has_method("apply_expression"):
		expression_report = blendshape_driver.apply_expression(expression, mood, intensity)
		if visemes is Array and blendshape_driver.has_method("play_viseme_timeline"):
			blendshape_driver.play_viseme_timeline(visemes, float(state.get("timestamp", 0.0)))

	var motion_driver: Node = _resolve_node(motion_driver_path)
	var motion_report := {"active_motion": null, "observed_nodes": {}}
	if motion_driver and motion_driver.has_method("apply_motion"):
		motion_driver.apply_motion(motion)
		if motion_driver.has_method("renderer_report"):
			motion_report = motion_driver.renderer_report()
	var speech_report := {"status": "not_requested", "phoneme_claimed": false}
	var timing_metadata: Variant = command_metadata.get("speech_timing", {})
	if typeof(timing_metadata) == TYPE_DICTIONARY:
		var timing_event := str((timing_metadata as Dictionary).get("event", ""))
		if timing_event in ["speech_started", "word_started", "speech_finished",
				"speech_interrupted", "speech_failed"]:
			var speaking_now := timing_event in ["speech_started", "word_started"]
			if blendshape_driver and blendshape_driver.has_method("set_speech_activity"):
				speech_report = blendshape_driver.set_speech_activity(speaking_now, timing_event)
			else:
				speech_report = {"status": "unavailable", "reason": "speech_renderer_unavailable",
					"timing_event": timing_event, "phoneme_claimed": false}
	var candidate_report := {"status": "not_loaded"}
	var candidate_adapter: Node = _resolve_node(candidate_body_adapter_path)
	if candidate_adapter and candidate_adapter.has_method("is_candidate_active") \
			and candidate_adapter.is_candidate_active():
		var candidate_expression: Dictionary = candidate_adapter.apply_expression(expression, intensity)
		var candidate_visemes: Dictionary = candidate_adapter.play_viseme_timeline(
			visemes, float(state.get("timestamp", 0.0)))
		var candidate_speech := {"status": "not_requested", "phoneme_claimed": false}
		if typeof(timing_metadata) == TYPE_DICTIONARY:
			var candidate_timing_event := str((timing_metadata as Dictionary).get("event", ""))
			if candidate_timing_event in ["speech_started", "word_started", "speech_finished",
					"speech_interrupted", "speech_failed"]:
				candidate_speech = candidate_adapter.set_speech_activity(
					candidate_timing_event in ["speech_started", "word_started"],
					candidate_timing_event)
		var candidate_motion: Dictionary = candidate_adapter.apply_motion(motion)
		candidate_report = candidate_adapter.renderer_report()
		candidate_report["expression"] = candidate_expression
		candidate_report["visemes"] = candidate_visemes
		candidate_report["speech"] = candidate_speech
		candidate_report["motion"] = candidate_motion
		_record_candidate_renderer_report(state, candidate_report, apply_started_usec)
	else:
		_last_candidate_renderer_report = {}
	_record_renderer_report(state, workload_mode, expression, mood, intensity, motion,
		expression_report, motion_report, speech_report, frame_delta_seconds,
		apply_started_usec)


func install_experimental_candidate(candidate_scene: PackedScene, evidence: Dictionary,
		motion_bones: Dictionary, expression_shapes: Dictionary,
		viseme_shapes: Dictionary, speech_activity_shape: String = "") -> Dictionary:
	var adapter: Node = _resolve_node(candidate_body_adapter_path)
	if adapter == null or not adapter.has_method("install_candidate"):
		return {"status": "unavailable", "reason": "candidate_body_adapter_unavailable"}
	return adapter.install_candidate(candidate_scene, evidence, motion_bones,
		expression_shapes, viseme_shapes, speech_activity_shape)


func _record_renderer_report(state: Dictionary, workload_mode: String, expression: String,
		mood: String, intensity: float, motion: String, expression_report: Dictionary,
		motion_report: Dictionary, speech_report: Dictionary,
		frame_delta_seconds: float, apply_started_usec: int) -> void:
	_report_sequence += 1
	var metadata: Variant = state.get("metadata", {})
	var command_metadata: Dictionary = metadata if metadata is Dictionary else {}
	var report := {
		"schema_version": "sentientos.avatar_renderer_report:v2",
		"evidence_class": "avatar_renderer_reported_state",
		"source_id": "godot-procedural-demo",
		"renderer_generation_id": _renderer_generation_id,
		"sequence": _report_sequence,
		"reported_at": Time.get_datetime_string_from_system(true, false) + "Z",
		"session_id": command_metadata.get("session_id"),
		"turn_id": command_metadata.get("turn_id"),
		"output_digest": command_metadata.get("output_digest"),
		"output_mode": command_metadata.get("output_mode"),
		"commanded_state": {"expression": expression, "mood": mood, "intensity": intensity,
			"motion": motion, "workload_mode": workload_mode},
		"renderer_state": {"expression": expression_report, "motion": motion_report,
			"speech": speech_report,
			"applied_render_cap_fps": Engine.max_fps},
		"frame_delta_seconds": frame_delta_seconds if frame_delta_seconds >= 0 else null,
		"apply_duration_usec": maxi(0, Time.get_ticks_usec() - apply_started_usec),
		"body_generation": "godot-procedural-demo-unadopted",
		"effect_proven": false,
		"independent_observation": false,
	}
	var hash_context := HashingContext.new()
	hash_context.start(HashingContext.HASH_SHA256)
	hash_context.update(JSON.stringify(report, "", true).to_utf8_buffer())
	report["source_digest"] = "sha256:" + hash_context.finish().hex_encode()
	_last_renderer_report = report
	_send_renderer_report(report)


func _send_renderer_report(report: Dictionary) -> void:
	if _renderer_report_sender == null:
		return
	var encoded := JSON.stringify(report).to_utf8_buffer()
	if encoded.is_empty() or encoded.size() > 60000:
		_write_status("Renderer report exceeds relay packet limit")
		return
	var result := _renderer_report_sender.put_packet(encoded)
	if result != OK:
		_write_status("Renderer report relay send failed (%s)" % error_string(result))


func _exit_tree() -> void:
	if _renderer_report_sender != null:
		_renderer_report_sender.close()


func _record_candidate_renderer_report(state: Dictionary, candidate_state: Dictionary,
		apply_started_usec: int) -> void:
	_candidate_report_sequence += 1
	var metadata_value: Variant = state.get("metadata", {})
	var metadata: Dictionary = metadata_value if metadata_value is Dictionary else {}
	var report := {
		"schema_version": "sentientos.experimental_candidate_avatar_renderer_report:v1",
		"evidence_class": "experimental_candidate_avatar_renderer_report",
		"renderer_generation_id": _renderer_generation_id,
		"sequence": _candidate_report_sequence,
		"reported_at": Time.get_datetime_string_from_system(true, false) + "Z",
		"session_id": metadata.get("session_id"),
		"turn_id": metadata.get("turn_id"),
		"output_digest": metadata.get("output_digest"),
		"candidate_state": candidate_state.duplicate(true),
		"commanded_state": {"expression": str(state.get("expression", "rest")),
			"motion": str(state.get("motion", "idle")),
			"intensity": float(state.get("intensity", 0.0))},
		"apply_duration_usec": maxi(0, Time.get_ticks_usec() - apply_started_usec),
		"effect_proven": false,
		"independent_observation": false,
	}
	var hash_context := HashingContext.new()
	hash_context.start(HashingContext.HASH_SHA256)
	hash_context.update(JSON.stringify(report, "", true).to_utf8_buffer())
	report["source_digest"] = "sha256:" + hash_context.finish().hex_encode()
	_last_candidate_renderer_report = report


func latest_renderer_report() -> Dictionary:
	return _last_renderer_report.duplicate(true)


func latest_candidate_renderer_report() -> Dictionary:
	return _last_candidate_renderer_report.duplicate(true)


func _set_workload_mode(workload_mode: String) -> void:
	# This caps only the companion renderer process. It does not change host or
	# game scheduling and does not claim to reserve system resources.
	Engine.max_fps = GAMING_RENDER_FPS if workload_mode == "gaming" else NORMAL_RENDER_FPS


func _write_status(message: String) -> void:
	var label: Label = _resolve_label(status_label_path)
	if label and label.has_method("set_text"):
		label.text = message


func _is_generation_id(value: String) -> bool:
	if value.is_empty() or value.length() > 128:
		return false
	var pattern := RegEx.new()
	if pattern.compile("^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$") != OK:
		return false
	return pattern.search(value) != null


func _resolve_node(path: NodePath) -> Node:
	if path == NodePath(""):
		return null
	return get_node_or_null(path)


func _resolve_label(path: NodePath) -> Label:
	if path == NodePath(""):
		return null
	return get_node_or_null(path) as Label
