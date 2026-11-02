extends Node3D

const _ALLOWED_MOTIONS := ["idle", "wave", "nod"]
const _ALLOWED_EXPRESSIONS := ["smile", "frown", "rest"]
const _ALLOWED_VISEMES := ["a", "e", "i", "o", "u", "neutral"]

var _candidate_root: Node3D
var _skeleton: Skeleton3D
var _candidate_identity := {}
var _motion_bones := {}
var _expression_shapes := {}
var _viseme_shapes := {}
var _active_motion := "idle"
var _active_expression_mesh: MeshInstance3D
var _active_expression_shape := ""
var _viseme_tween: Tween


func install_candidate(candidate_scene: PackedScene, evidence: Dictionary,
		motion_bones: Dictionary, expression_shapes: Dictionary,
		viseme_shapes: Dictionary) -> Dictionary:
	if not candidate_scene is PackedScene:
		return {"status": "rejected", "reason": "candidate_scene_invalid"}
	if evidence.get("result_posture") != "candidate_validated":
		return {"status": "rejected", "reason": "candidate_validation_evidence_required"}
	var artifact_digest: String = str(evidence.get("artifact_sha256", ""))
	var receipt_digest: String = str(evidence.get("receipt_digest", ""))
	if not _is_digest(artifact_digest):
		return {"status": "rejected", "reason": "candidate_artifact_digest_invalid"}
	if not _is_digest(receipt_digest):
		return {"status": "rejected", "reason": "candidate_receipt_digest_invalid"}
	var authority_value: Variant = evidence.get("authority", {})
	if typeof(authority_value) != TYPE_DICTIONARY or (authority_value as Dictionary).is_empty():
		return {"status": "rejected", "reason": "candidate_authority_evidence_invalid"}
	for authority_flag in (authority_value as Dictionary).values():
		if typeof(authority_flag) != TYPE_BOOL or authority_flag:
			return {"status": "rejected", "reason": "candidate_adoption_authority_forbidden"}
	var predecessor_generation: Variant = evidence.get("predecessor_generation")
	if (typeof(predecessor_generation) != TYPE_INT and typeof(predecessor_generation) != TYPE_FLOAT):
		return {"status": "rejected", "reason": "candidate_generation_evidence_invalid"}
	var predecessor_generation_number := float(predecessor_generation)
	if (not is_finite(predecessor_generation_number) or predecessor_generation_number < 0.0
			or not is_equal_approx(predecessor_generation_number, round(predecessor_generation_number))):
		return {"status": "rejected", "reason": "candidate_generation_evidence_invalid"}
	var artifact_path: String = candidate_scene.resource_path
	if artifact_path.is_empty():
		return {"status": "rejected", "reason": "candidate_artifact_path_unavailable"}
	var artifact_bytes := FileAccess.get_file_as_bytes(artifact_path)
	if artifact_bytes.is_empty():
		return {"status": "rejected", "reason": "candidate_artifact_unavailable"}
	var hash_context := HashingContext.new()
	hash_context.start(HashingContext.HASH_SHA256)
	hash_context.update(artifact_bytes)
	var observed_digest := "sha256:" + hash_context.finish().hex_encode()
	if observed_digest != artifact_digest:
		return {"status": "rejected", "reason": "candidate_artifact_digest_mismatch"}

	var instance_value: Node = candidate_scene.instantiate()
	if not instance_value is Node3D:
		instance_value.free()
		return {"status": "rejected", "reason": "candidate_root_not_3d"}
	var skeletons := instance_value.find_children("*", "Skeleton3D", true, false)
	if skeletons.size() != 1:
		instance_value.free()
		return {"status": "rejected", "reason": "candidate_skeleton_ambiguous_or_missing"}
	var candidate_skeleton := skeletons[0] as Skeleton3D
	var validated_motion_bones := _validate_bone_mappings(candidate_skeleton, motion_bones)
	if not validated_motion_bones.valid:
		instance_value.free()
		return {"status": "rejected", "reason": validated_motion_bones.reason}
	if not _validate_shape_mappings(expression_shapes, _ALLOWED_EXPRESSIONS):
		instance_value.free()
		return {"status": "rejected", "reason": "candidate_expression_mapping_invalid"}
	if not _validate_shape_mappings(viseme_shapes, _ALLOWED_VISEMES):
		instance_value.free()
		return {"status": "rejected", "reason": "candidate_viseme_mapping_invalid"}

	if _candidate_root:
		_candidate_root.queue_free()
	_candidate_root = instance_value
	_skeleton = candidate_skeleton
	_candidate_identity = {
		"evidence_posture": "caller_supplied_candidate_validation",
		"body_id": str(evidence.get("body_id", "")),
		"candidate_generation": int(predecessor_generation_number) + 1,
		"artifact_sha256": observed_digest,
		"authoring_receipt_digest": receipt_digest,
		"adopted": false,
	}
	_motion_bones = validated_motion_bones.mapping
	_expression_shapes = expression_shapes.duplicate(true)
	_viseme_shapes = viseme_shapes.duplicate(true)
	add_child(_candidate_root)
	return {"status": "candidate_loaded_unadopted", "identity": _candidate_identity.duplicate(true)}


func is_candidate_active() -> bool:
	return _candidate_root != null and _skeleton != null


func apply_motion(motion: String) -> Dictionary:
	if not is_candidate_active():
		return {"status": "unavailable", "reason": "candidate_not_loaded"}
	if motion not in _ALLOWED_MOTIONS:
		return {"status": "unsupported", "reason": "motion_not_in_closed_mapping", "motion": motion}
	if motion == "idle":
		for mapped_bone in _motion_bones.values():
			var rest_index := _skeleton.find_bone(str(mapped_bone))
			if rest_index >= 0:
				_skeleton.set_bone_pose_rotation(rest_index,
					_skeleton.get_bone_rest(rest_index).basis.get_rotation_quaternion())
		_active_motion = "idle"
		return {"status": "applied", "active_motion": _active_motion, "bone": null}
	if not _motion_bones.has(motion):
		return {"status": "unsupported", "reason": "motion_mapping_unavailable", "motion": motion}
	var bone_name: String = _motion_bones[motion]
	var bone_index := _skeleton.find_bone(bone_name)
	if bone_index < 0:
		return {"status": "unsupported", "reason": "mapped_bone_unavailable", "motion": motion}
	var rest := _skeleton.get_bone_rest(bone_index).basis.get_rotation_quaternion()
	var axis := Vector3.FORWARD if motion == "wave" else Vector3.RIGHT
	var angle := -0.55 if motion == "wave" else 0.28
	var pose := rest * Quaternion(axis, angle)
	_skeleton.set_bone_pose_rotation(bone_index, pose)
	_active_motion = motion
	return {"status": "applied", "active_motion": motion, "bone": bone_name,
		"bone_pose_rotation": _quaternion_payload(pose)}


func apply_expression(expression: String, intensity: float) -> Dictionary:
	if not is_candidate_active():
		return {"status": "unavailable", "reason": "candidate_not_loaded"}
	if expression not in _ALLOWED_EXPRESSIONS:
		return {"status": "unsupported", "reason": "expression_not_in_closed_mapping"}
	_reset_expression()
	var shape_name: String = str(_expression_shapes.get(expression, ""))
	var found := _find_shape(shape_name)
	if not found.is_empty():
		var mesh_node := found["mesh"] as MeshInstance3D
		mesh_node.set_blend_shape_value(found["index"], clampf(intensity, 0.0, 1.0))
		_active_expression_mesh = mesh_node
		_active_expression_shape = shape_name
		return {"status": "blend_shape_applied", "shape": shape_name,
			"weight": mesh_node.get_blend_shape_value(found["index"])}
	return {"status": "unsupported", "reason": "candidate_expression_shape_unavailable",
		"requested_shape": shape_name if not shape_name.is_empty() else null}


func play_viseme_timeline(timeline: Array, anchor_timestamp: float = 0.0) -> Dictionary:
	if not is_candidate_active():
		return {"status": "unavailable", "reason": "candidate_not_loaded"}
	if _viseme_tween:
		_viseme_tween.kill()
	if timeline.is_empty():
		return {"status": "not_requested", "cue_count": 0}
	var first_value: Variant = timeline[0]
	if typeof(first_value) != TYPE_DICTIONARY:
		return {"status": "unsupported", "reason": "viseme_cue_invalid"}
	var viseme: String = str(first_value.get("viseme", first_value.get("value", "neutral"))).to_lower()
	if viseme not in _ALLOWED_VISEMES:
		return {"status": "unsupported", "reason": "viseme_not_in_closed_mapping"}
	var shape_name: String = str(_viseme_shapes.get(viseme, ""))
	var found := _find_shape(shape_name)
	if found.is_empty():
		return {"status": "unsupported", "reason": "candidate_viseme_shape_unavailable",
			"requested_shape": shape_name if not shape_name.is_empty() else null,
			"cue_count": timeline.size()}
	var elapsed := 0.0
	if anchor_timestamp > 0.0:
		elapsed = maxf(0.0, Time.get_unix_time_from_system() - anchor_timestamp)
	var start := maxf(0.0, float(first_value.get("time", 0.0)) - elapsed)
	var duration := maxf(0.05, float(first_value.get("duration", 0.05)))
	var mesh_node := found["mesh"] as MeshInstance3D
	_viseme_tween = create_tween()
	_viseme_tween.tween_callback(_set_candidate_shape.bind(mesh_node, shape_name, 0.75)).set_delay(start)
	_viseme_tween.tween_callback(_set_candidate_shape.bind(mesh_node, shape_name, 0.0)).set_delay(start + duration)
	return {"status": "blend_shape_applied", "shape": shape_name, "cue_count": timeline.size()}


func renderer_report() -> Dictionary:
	return {"status": "candidate_loaded_unadopted" if is_candidate_active() else "not_loaded",
		"identity": _candidate_identity.duplicate(true), "active_motion": _active_motion,
		"expression": {"status": "not_requested"}, "visemes": {"status": "not_requested"}}


func _validate_bone_mappings(skeleton: Skeleton3D, mappings: Dictionary) -> Dictionary:
	var result := {}
	for motion_value in mappings:
		var motion: String = str(motion_value)
		var bone: String = str(mappings[motion_value])
		if motion not in ["wave", "nod"] or bone.is_empty() or skeleton.find_bone(bone) < 0:
			return {"valid": false, "reason": "candidate_motion_mapping_invalid"}
		result[motion] = bone
	return {"valid": true, "mapping": result}


func _validate_shape_mappings(mappings: Dictionary, allowed: Array) -> bool:
	for key_value in mappings:
		var key: String = str(key_value)
		var value: String = str(mappings[key_value])
		if key not in allowed or value.is_empty() or value.length() > 128:
			return false
	return true


func _is_digest(value: String) -> bool:
	if value.length() != 71 or not value.begins_with("sha256:"):
		return false
	for character in value.substr(7):
		if "0123456789abcdef".find(character) < 0:
			return false
	return true


func _reset_expression() -> void:
	if _active_expression_mesh and not _active_expression_shape.is_empty():
		var index := _blend_shape_index(_active_expression_mesh, _active_expression_shape)
		if index >= 0:
			_active_expression_mesh.set_blend_shape_value(index, 0.0)
	_active_expression_mesh = null
	_active_expression_shape = ""


func _set_candidate_shape(mesh_node: MeshInstance3D, shape_name: String, weight: float) -> void:
	var index := _blend_shape_index(mesh_node, shape_name)
	if index >= 0:
		mesh_node.set_blend_shape_value(index, clampf(weight, 0.0, 1.0))


func _blend_shape_index(mesh_node: MeshInstance3D, shape_name: String) -> int:
	if not mesh_node.mesh is ArrayMesh:
		return -1
	return (mesh_node.mesh as ArrayMesh).find_blend_shape_by_name(shape_name)


func _find_shape(shape_name: String) -> Dictionary:
	if shape_name.is_empty():
		return {}
	for node in _candidate_root.find_children("*", "MeshInstance3D", true, false):
		var mesh_node := node as MeshInstance3D
		if not mesh_node.mesh is ArrayMesh:
			continue
		var mesh := mesh_node.mesh as ArrayMesh
		var shape_index: int = mesh.find_blend_shape_by_name(shape_name)
		if shape_index >= 0:
			return {"mesh": mesh_node, "index": shape_index}
	return {}


func _quaternion_payload(value: Quaternion) -> Dictionary:
	return {"x": value.x, "y": value.y, "z": value.z, "w": value.w}
