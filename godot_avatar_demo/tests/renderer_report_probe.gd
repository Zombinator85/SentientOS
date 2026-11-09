extends SceneTree


func _initialize() -> void:
	call_deferred("_run_probe")


func _run_probe() -> void:
	var packed: Variant = load("res://scenes/avatar_demo.tscn")
	if not packed is PackedScene:
		push_error("renderer_probe_scene_load_failed")
		quit(1)
		return
	var avatar: Node = packed.instantiate()
	avatar.set("auto_listen", false)
	root.add_child(avatar)
	var state := {
		"expression": "smile",
		"mood": "joy",
		"intensity": 0.8,
		"motion": "wave",
		"workload_mode": "gaming",
		"metadata": {
			"session_id": "session-1",
			"turn_id": "turn-2",
			"output_digest": "a".repeat(64),
			"output_mode": "chat_response_visual_only",
		},
	}
	var user_args := OS.get_cmdline_user_args()
	if not user_args.is_empty():
		var supplied: Variant = JSON.parse_string(user_args[0])
		if typeof(supplied) != TYPE_DICTIONARY:
			push_error("renderer_probe_input_not_object")
			quit(1)
			return
		state = supplied as Dictionary
	avatar.call("_apply_state", state, 0.016)
	var report: Dictionary = avatar.call("latest_renderer_report")
	var motion: Dictionary = report.get("renderer_state", {}).get("motion", {})
	var expression: Dictionary = report.get("renderer_state", {}).get("expression", {})
	var arm_rotation: Dictionary = motion.get("left_arm_rotation_radians", {})
	if report.get("schema_version") != "sentientos.avatar_renderer_report:v2":
		push_error("renderer_probe_schema_invalid")
		quit(1)
		return
	var metadata_value: Variant = state.get("metadata", {})
	var command_metadata: Dictionary = metadata_value if metadata_value is Dictionary else {}
	if (report.get("session_id") != command_metadata.get("session_id")
			or report.get("turn_id") != command_metadata.get("turn_id")
			or report.get("output_digest") != command_metadata.get("output_digest")):
		push_error("renderer_probe_command_lineage_missing")
		quit(1)
		return
	for field in ["consequence_expectation_id", "consequence_expectation_digest",
			"consequence_handoff_id", "consequence_handoff_digest",
			"consequence_correlation_id"]:
		if command_metadata.has(field) and report.get(field) != command_metadata.get(field):
			push_error("renderer_probe_consequence_lineage_missing")
			quit(1)
			return
	if motion.get("active_motion") != state.get("motion"):
		push_error("renderer_probe_motion_not_applied")
		quit(1)
		return
	if motion.get("active_motion") == "wave" and float(arm_rotation.get("z", 0.0)) >= -0.14:
		push_error("renderer_probe_transform_not_observed")
		quit(1)
		return
	if not str(expression.get("status", "")).ends_with("applied"):
		push_error("renderer_probe_expression_fallback_not_reported")
		quit(1)
		return
	if report.get("effect_proven") != false or report.get("independent_observation") != false:
		push_error("renderer_probe_evidence_boundary_invalid")
		quit(1)
		return
	var expected_cap := 15 if state.get("workload_mode") == "gaming" else 60
	if report.get("renderer_state", {}).get("applied_render_cap_fps") != expected_cap:
		push_error("renderer_probe_workload_cap_missing")
		quit(1)
		return
	if not str(report.get("source_digest", "")).begins_with("sha256:"):
		push_error("renderer_probe_source_digest_missing")
		quit(1)
		return
	print("sentientos_renderer_report_json:" + JSON.stringify(report))
	print("godot_renderer_report_probe_passed")
	avatar.queue_free()
	quit(0)
