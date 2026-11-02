extends SceneTree


func _initialize() -> void:
	var demo_value: Variant = load("res://scenes/avatar_demo.tscn")
	if not demo_value is PackedScene:
		_fail("candidate_probe_demo_scene_unavailable")
		return
	var demo := (demo_value as PackedScene).instantiate()
	demo.set("auto_listen", false)
	root.add_child(demo)
	await process_frame
	var candidate_value: Variant = load("res://candidate.glb")
	if not candidate_value is PackedScene:
		_fail("candidate_probe_glb_not_packed_scene")
		return
	var arguments := OS.get_cmdline_user_args()
	if arguments.is_empty():
		_fail("candidate_probe_evidence_missing")
		return
	var evidence_value: Variant = JSON.parse_string(arguments[0])
	if typeof(evidence_value) != TYPE_DICTIONARY:
		_fail("candidate_probe_evidence_invalid")
		return
	var evidence := evidence_value as Dictionary
	var adapter := demo.get_node("CandidateBodyAdapter")
	var fractional_evidence := evidence.duplicate(true)
	fractional_evidence["predecessor_generation"] = 1.5
	var fractional_result: Dictionary = adapter.install_candidate(candidate_value as PackedScene,
		fractional_evidence, {"wave": "upper"}, {}, {})
	if fractional_result.get("reason") != "candidate_generation_evidence_invalid":
		_fail("candidate_probe_fractional_generation_accepted")
		return
	var negative_evidence := evidence.duplicate(true)
	negative_evidence["predecessor_generation"] = -1
	var negative_result: Dictionary = adapter.install_candidate(candidate_value as PackedScene,
		negative_evidence, {"wave": "upper"}, {}, {})
	if negative_result.get("reason") != "candidate_generation_evidence_invalid":
		_fail("candidate_probe_negative_generation_accepted")
		return
	var install_result: Dictionary = demo.install_experimental_candidate(
		candidate_value as PackedScene, evidence,
		{"wave": "upper", "nod": "upper"},
		{"smile": "smile", "frown": "FaceFrown", "rest": "FaceNeutral"}, {}, "MouthOpen")
	if install_result.get("status") != "candidate_loaded_unadopted":
		_fail("candidate_probe_install_failed:" + str(install_result))
		return
	var meshes := adapter.find_children("*", "MeshInstance3D", true, false)
	var skeletons := adapter.find_children("*", "Skeleton3D", true, false)
	if meshes.is_empty() or skeletons.size() != 1:
		_fail("candidate_probe_mesh_or_skeleton_missing")
		return
	var expected_color := Vector3(pow(0.11, 1.0 / 2.2), pow(0.57, 1.0 / 2.2), pow(0.65, 1.0 / 2.2))
	var color_survived := false
	for mesh_node_value in meshes:
		var mesh_node := mesh_node_value as MeshInstance3D
		if mesh_node.mesh == null:
			continue
		for surface_index in range(mesh_node.mesh.get_surface_count()):
			var material := mesh_node.mesh.surface_get_material(surface_index) as StandardMaterial3D
			if material and Vector3(material.albedo_color.r, material.albedo_color.g,
					material.albedo_color.b).distance_to(expected_color) < 0.01:
				color_survived = true
	if not color_survived:
		_fail("candidate_probe_material_mapping_missing")
		return
	var state := {
		"expression": "smile", "mood": "joy", "intensity": 0.8,
		"motion": "wave", "workload_mode": "gaming",
		"metadata": {"session_id": "candidate-session", "turn_id": "candidate-turn",
			"output_digest": "d".repeat(64), "output_mode": "chat_response_visual_only",
			"speech_timing": {"event": "speech_started"}},
		"viseme_timeline": [{"time": 0.0, "duration": 0.1, "viseme": "a"}],
	}
	demo.call("_apply_state", state, 0.016)
	var candidate_report: Dictionary = demo.latest_candidate_renderer_report()
	var candidate_state: Dictionary = candidate_report.get("candidate_state", {})
	var identity: Dictionary = candidate_state.get("identity", {})
	if identity.get("artifact_sha256") != evidence.get("artifact_sha256"):
		_fail("candidate_probe_artifact_identity_mismatch")
		return
	if identity.get("adopted") != false:
		_fail("candidate_probe_candidate_marked_adopted")
		return
	var motion: Dictionary = candidate_state.get("motion", {})
	if motion.get("status") != "applied" or motion.get("bone") != "upper":
		_fail("candidate_probe_motion_mapping_not_applied")
		return
	if motion.get("motion_source") != "authored_gltf_animation":
		_fail("candidate_probe_authored_motion_clip_not_used")
		return
	if motion.get("animation_clip") != "wave":
		_fail("candidate_probe_authored_motion_clip_mismatch")
		return
	var animation_players := adapter.find_children("*", "AnimationPlayer", true, false)
	if animation_players.size() != 1:
		_fail("candidate_probe_animation_player_missing_or_ambiguous")
		return
	var animation_player := animation_players[0] as AnimationPlayer
	if not animation_player.is_playing() or animation_player.current_animation != "wave":
		_fail("candidate_probe_authored_motion_clip_not_playing")
		return
	var idle_motion: Dictionary = adapter.apply_motion("idle")
	if idle_motion.get("status") != "applied" or idle_motion.get("motion_source") != "rest_pose":
		_fail("candidate_probe_idle_motion_not_applied")
		return
	if animation_player.is_playing():
		_fail("candidate_probe_authored_motion_clip_did_not_stop_for_idle")
		return
	var resumed_motion: Dictionary = adapter.apply_motion("wave")
	if resumed_motion.get("status") != "applied" or not animation_player.is_playing():
		_fail("candidate_probe_authored_motion_clip_did_not_resume")
		return
	if candidate_state.get("expression", {}).get("status") != "blend_shape_applied":
		_fail("candidate_probe_authored_expression_not_applied")
		return
	if candidate_state.get("expression", {}).get("shape") != "smile":
		_fail("candidate_probe_authored_expression_shape_mismatch")
		return
	if not is_equal_approx(float(candidate_state.get("expression", {}).get("weight", 0.0)), 0.8):
		_fail("candidate_probe_authored_expression_weight_mismatch")
		return
	if candidate_state.get("visemes", {}).get("status") != "unsupported":
		_fail("candidate_probe_missing_viseme_not_reported")
		return
	if candidate_state.get("speech", {}).get("status") != "speaking" \
			or candidate_state.get("speech", {}).get("phoneme_claimed") != false:
		_fail("candidate_probe_authored_speech_activity_not_applied:" +
			JSON.stringify(candidate_state.get("speech", {})))
		return
	var mouth_open_mesh: MeshInstance3D
	var mouth_open_index: int = -1
	for mesh_value in meshes:
		var candidate_mesh := mesh_value as MeshInstance3D
		if candidate_mesh.mesh != null:
			for shape_index in range(candidate_mesh.mesh.get_blend_shape_count()):
				if candidate_mesh.mesh.get_blend_shape_name(shape_index) == "MouthOpen":
					mouth_open_index = shape_index
					mouth_open_mesh = candidate_mesh
					break
			if mouth_open_index >= 0:
				break
	if mouth_open_mesh == null or mouth_open_index < 0 \
			or not is_equal_approx(mouth_open_mesh.get_blend_shape_value(mouth_open_index), 0.38):
		_fail("candidate_probe_speech_activity_shape_weight_invalid")
		return
	state["metadata"]["speech_timing"] = {"event": "speech_interrupted"}
	demo.call("_apply_state", state, 0.016)
	var interrupted_report: Dictionary = demo.latest_candidate_renderer_report()
	if interrupted_report.get("candidate_state", {}).get("speech", {}).get("status") != "idle":
		_fail("candidate_probe_interruption_did_not_close_speech_activity")
		return
	if not is_equal_approx(mouth_open_mesh.get_blend_shape_value(mouth_open_index), 0.0):
		_fail("candidate_probe_interruption_left_authored_mouth_open")
		return
	if candidate_report.get("effect_proven") != false or candidate_report.get("independent_observation") != false:
		_fail("candidate_probe_evidence_posture_invalid")
		return
	print("sentientos_candidate_renderer_report_json:" + JSON.stringify(candidate_report))
	print("SENTIENTOS_GLB_SCENE_READY meshes=%d skeletons=%d" % [meshes.size(), skeletons.size()])
	print("sentientos_candidate_renderer_probe_passed")
	print("sentientos_authored_motion_clip_playing name=wave")
	quit(0)


func _fail(reason: String) -> void:
	push_error(reason)
	quit(1)
