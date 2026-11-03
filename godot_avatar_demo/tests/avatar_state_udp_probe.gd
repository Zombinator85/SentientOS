extends SceneTree

var _avatar: Node
var _deadline_msec := 0


func _initialize() -> void:
	call_deferred("_start_probe")


func _start_probe() -> void:
	var port_text := OS.get_environment("SENTIENTOS_GODOT_LISTEN_PORT")
	if not port_text.is_valid_int():
		push_error("avatar_state_probe_port_invalid")
		quit(1)
		return
	var packed: Variant = load("res://scenes/avatar_demo.tscn")
	if not packed is PackedScene:
		push_error("avatar_state_probe_scene_load_failed")
		quit(1)
		return
	_avatar = packed.instantiate()
	_avatar.set("listen_port", port_text.to_int())
	_avatar.set("auto_listen", true)
	root.add_child(_avatar)
	print("godot_avatar_state_listener_ready:%d" % port_text.to_int())
	var timer := Timer.new()
	timer.wait_time = 0.02
	timer.timeout.connect(_poll_report)
	root.add_child(timer)
	timer.start()
	_deadline_msec = Time.get_ticks_msec() + 8000


func _poll_report() -> void:
	var report_value: Variant = _avatar.call("latest_renderer_report")
	if not report_value is Dictionary or (report_value as Dictionary).is_empty():
		if Time.get_ticks_msec() >= _deadline_msec:
			push_error("avatar_state_probe_report_timeout")
			quit(1)
		return
	var report := report_value as Dictionary
	var commanded: Dictionary = report.get("commanded_state", {})
	var renderer_state: Dictionary = report.get("renderer_state", {})
	if (report.get("schema_version") != "sentientos.avatar_renderer_report:v2"
			or report.get("session_id") != "cross-host-test"
			or report.get("turn_id") != "smoke-turn"
			or report.get("output_digest") != "d".repeat(64)
			or report.get("output_mode") != "chat_response_visual_only"
			or commanded.get("workload_mode") != "gaming"
			or renderer_state.get("applied_render_cap_fps") != 15
			or report.get("effect_proven") != false
			or report.get("independent_observation") != false):
		push_error("avatar_state_probe_command_lineage_invalid")
		quit(1)
		return
	print("sentientos_renderer_report_json:" + JSON.stringify(report))
	print("godot_avatar_state_queue_probe_passed")
	quit(0)
