extends SceneTree


func _initialize() -> void:
	call_deferred("_run_probe")


func _run_probe() -> void:
	var packed: Variant = load("res://scenes/avatar_demo.tscn")
	if not packed is PackedScene:
		_fail("speech_probe_scene_unavailable")
		return
	var avatar: Node = packed.instantiate()
	avatar.set("auto_listen", false)
	root.add_child(avatar)
	var base_state := {"expression": "rest", "mood": "calm", "intensity": 0.0,
		"motion": "idle", "current_phrase": "Hello there",
		"metadata": {"session_id": "speech-session", "turn_id": "speech-turn",
			"output_digest": "e".repeat(64), "output_mode": "chat_response_visual_only",
			"speech_timing": {"schema": "sentientos.local_speech_timing:v1",
				"event": "speech_started", "timing_quality": "controller_boundary"}}}
	avatar.call("_apply_state", base_state, 0.016)
	var active_report: Dictionary = avatar.call("latest_renderer_report")
	var active_speech: Dictionary = active_report.get("renderer_state", {}).get("speech", {})
	if active_speech.get("status") != "speaking" or active_speech.get("phoneme_claimed") != false:
		_fail("speech_probe_activity_not_reported_truthfully")
		return
	var ended_state: Dictionary = base_state.duplicate(true)
	ended_state["metadata"]["speech_timing"]["event"] = "speech_interrupted"
	avatar.call("_apply_state", ended_state, 0.016)
	var ended_report: Dictionary = avatar.call("latest_renderer_report")
	var ended_speech: Dictionary = ended_report.get("renderer_state", {}).get("speech", {})
	if ended_speech.get("status") != "idle" or float(ended_speech.get("mouth_weight", 1.0)) != 0.0:
		_fail("speech_probe_interruption_did_not_close_mouth")
		return
	print("sentientos_speech_activity_probe_passed")
	avatar.queue_free()
	quit(0)


func _fail(reason: String) -> void:
	push_error(reason)
	quit(1)
