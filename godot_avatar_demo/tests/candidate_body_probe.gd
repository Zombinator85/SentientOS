extends SceneTree


func _initialize() -> void:
	var demo_value: Variant = load("res://scenes/avatar_demo.tscn")
	if not demo_value is PackedScene:
		_fail("candidate_probe_demo_scene_unavailable")
		return
	var demo := (demo_value as PackedScene).instantiate()
	demo.set("auto_listen", false)
	root.add_child(demo)
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
		{"smile": "FaceSmile", "frown": "FaceFrown", "rest": "FaceNeutral"},
		{"a": "MouthOpen", "e": "MouthOpen", "i": "MouthOpen", "o": "MouthOpen", "u": "MouthOpen"})
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
			var material := mesh_node.get_active_material(surface_index) as StandardMaterial3D
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
			"output_digest": "d".repeat(64), "output_mode": "chat_response_visual_only"},
		"viseme_timeline": [{"time": 0.0, "duration": 0.1, "viseme": "a"}],
	}
	demo.call("_apply_state", state, 0.016)
	var renderer_report: Dictionary = demo.latest_renderer_report()
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
	if motion.get("bone_pose_rotation", {}).get("z", 0.0) == 0.0:
		_fail("candidate_probe_bone_pose_not_changed")
		return
	if candidate_state.get("expression", {}).get("status") != "unsupported":
		_fail("candidate_probe_missing_expression_not_reported")
		return
	if candidate_state.get("visemes", {}).get("status") != "unsupported":
		_fail("candidate_probe_missing_viseme_not_reported")
		return
	if candidate_report.get("effect_proven") != false or candidate_report.get("independent_observation") != false:
		_fail("candidate_probe_evidence_posture_invalid")
		return
	print("sentientos_candidate_renderer_report_json:" + JSON.stringify(candidate_report))
	print("SENTIENTOS_GLB_SCENE_READY meshes=%d skeletons=%d" % [meshes.size(), skeletons.size()])
	print("sentientos_candidate_renderer_probe_passed")
	quit(0)


func _fail(reason: String) -> void:
	push_error(reason)
	quit(1)
