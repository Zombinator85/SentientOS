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
	avatar.call("_apply_state", {
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
	}, 0.016)
	var report: Dictionary = avatar.call("latest_renderer_report")
	var motion: Dictionary = report.get("renderer_state", {}).get("motion", {})
	var expression: Dictionary = report.get("renderer_state", {}).get("expression", {})
	var arm_rotation: Dictionary = motion.get("left_arm_rotation_radians", {})
	if report.get("schema_version") != "sentientos.avatar_renderer_report:v1":
		push_error("renderer_probe_schema_invalid")
		quit(1)
		return
	if report.get("turn_id") != "turn-2" or report.get("output_digest") != "a".repeat(64):
		push_error("renderer_probe_command_lineage_missing")
		quit(1)
		return
	if motion.get("active_motion") != "wave":
		push_error("renderer_probe_motion_not_applied")
		quit(1)
		return
	if float(arm_rotation.get("z", 0.0)) >= -0.14:
		push_error("renderer_probe_transform_not_observed")
		quit(1)
		return
	if expression.get("status") != "procedural_fallback_applied":
		push_error("renderer_probe_expression_fallback_not_reported")
		quit(1)
		return
	if report.get("effect_proven") != false or report.get("independent_observation") != false:
		push_error("renderer_probe_evidence_boundary_invalid")
		quit(1)
		return
	if report.get("renderer_state", {}).get("applied_render_cap_fps") != 15:
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
