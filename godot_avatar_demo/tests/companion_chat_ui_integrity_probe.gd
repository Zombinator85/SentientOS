extends SceneTree

var _probe_failures: PackedStringArray = PackedStringArray()


func _initialize():
	var ui_script: GDScript = load("res://scripts/companion_chat_ui.gd")
	var ui = ui_script.new()
	ui._build_interface()
	_check(not ui._chat_panel.visible, "chat hidden by default")
	_check(ui._chat_panel.offset_top == -604.0 and ui._chat_panel.offset_bottom == -16.0,
		"expanded chat panel leaves room for transcript and composer")
	var usable_area := Rect2i(Vector2i(100, 40), Vector2i(1920, 1040))
	_check(
		ui._clamped_window_position(Vector2i(1800, 950), Vector2i(360, 480), usable_area) == Vector2i(1660, 600),
		"expanded chat clamped inside display work area")
	_check(
		ui._clamped_window_position(Vector2i(500, 300), Vector2i(360, 480), usable_area) == Vector2i(500, 300),
		"visible chat position preserved")
	_check(
		ui._compact_position_from_expanded_window(Vector2i(600, 300), usable_area) == Vector2i(790, 520),
		"expanded chat drag maps back to the compact avatar anchor")
	_check(ui._overlay_drag_handle.text.contains("drag to move"), "visible overlay drag handle")
	_check(ui._overlay_drag_handle.mouse_filter == Control.MOUSE_FILTER_STOP,
		"overlay drag handle receives input")
	_check(ui._overlay_drag_handle.gui_input.is_connected(
		Callable(ui, "_on_overlay_drag_handle_input")), "overlay drag handler connected")
	var preference_config_path := "user://companion_preferences_probe.cfg"
	var saved_preferences := ConfigFile.new()
	ui._speech_output_preference_enabled = false
	ui._screen_observation_preference_enabled = false
	ui._write_preferences_to_config(saved_preferences)
	_check(saved_preferences.save(preference_config_path) == OK,
		"persistent voice and game-screen preferences save")
	var restored_preferences := ConfigFile.new()
	_check(restored_preferences.load(preference_config_path) == OK,
		"persistent preferences reload after restart")
	var restored_ui = ui_script.new()
	restored_ui._load_preferences_from_config(restored_preferences)
	_check(not restored_ui._speech_output_preference_enabled,
		"voice preference restores its saved value")
	_check(not restored_ui._screen_observation_preference_enabled,
		"game-screen preference restores its saved value")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(preference_config_path))
	restored_ui.free()
	_check(
		ui._default_overlay_position(usable_area) == Vector2i(1916, 988),
		"first-run avatar defaults to lower-right of display work area")
	var corners: Array[Vector2i] = ui._corner_positions(usable_area)
	_check(corners == [Vector2i(64, 36), Vector2i(1916, 36), Vector2i(64, 988), Vector2i(1916, 988)],
		"avatar placement exposes all four display corners")
	_check(ui._snap_compact_position_to_nearest_corner(Vector2i(145, 72), usable_area) == corners[0],
		"drop near upper-left snaps avatar into corner")
	_check(ui._snap_compact_position_to_nearest_corner(Vector2i(1848, 900), usable_area) == corners[3],
		"drop near lower-right snaps avatar into corner")
	_check(ui._snap_compact_position_to_nearest_corner(Vector2i(900, 400), usable_area) == Vector2i(900, 400),
		"interior avatar position remains freely movable")
	_check(ui._clamped_compact_position(Vector2i(-100, -100), usable_area) == corners[0],
		"avatar stays visible while transparent window padding extends past screen edges")
	ui._compact_window_position = Vector2i(420, 300)
	ui._has_compact_window_position = true
	ui._save_overlay_position()
	var overlay_config := ConfigFile.new()
	_check(overlay_config.load(ui.OVERLAY_POSITION_CONFIG) == OK,
		"compact avatar position saved to user config")
	_check(overlay_config.get_value("overlay", "compact_position") == Vector2i(420, 300),
		"dragged avatar position persists across relaunch")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(ui.OVERLAY_POSITION_CONFIG))
	var close_chat: Button = ui._overlay_drag_handle.get_parent().get_node("CloseChat")
	_check(close_chat.pressed.is_connected(Callable(ui, "_toggle_chat_visibility")),
		"chat close button connected")
	ui._set_chat_visible(true)
	_check(ui._chat_panel.visible, "chat can be opened")
	close_chat.pressed.emit()
	_check(not ui._chat_panel.visible, "chat close button hides chat")
	ui._handle_global_hotkey_packet("registered")
	_check(ui._global_hotkey_registered, "global shortcut registration acknowledged")
	ui._handle_global_hotkey_packet("sentientos.toggle_chat.v1")
	_check(ui._chat_panel.visible, "global shortcut opens chat")
	ui._handle_global_hotkey_packet("sentientos.toggle_chat.v1")
	_check(not ui._chat_panel.visible, "global shortcut closes chat")
	var hotkey_helper := FileAccess.get_file_as_string(
		"res://scripts/companion_global_hotkey.ps1")
	_check(hotkey_helper.contains("::RegisterHotKey"), "Windows helper registers system shortcut")
	_check(hotkey_helper.contains("0x0002 -bor 0x0004 -bor 0x4000")
		and hotkey_helper.contains("0x20"), "registered shortcut is Ctrl+Shift+Space")
	_check(not hotkey_helper.contains("SetWindowsHookEx"),
		"global shortcut does not install a keyboard hook")
	ui._session_id = "session-demo"
	ui._last_completed_turn_id = "turn-demo"
	ui._last_integrity_summary = "Displayed answer matches raw, transcript, and API digests."
	ui._update_session_status()
	_check(ui._session_status_label.tooltip_text.contains("session-demo"), "visible conversation ID")
	_check(ui._session_status_label.tooltip_text.contains("turn-demo"), "visible reply turn ID")
	_check(ui._session_status_label.tooltip_text.contains("Displayed answer matches"), "visible answer integrity")
	var answer := "A grounded answer."
	var digest := _sha256(answer)
	var exact: String = ui._summarize_answer_integrity({
		"status": "exact_invocation_output_match",
		"invocation_output_text_sha256": digest,
		"transcript_text_sha256": digest,
		"delivery_text_sha256": digest,
	}, answer)
	_check(exact == "Displayed answer matches raw, transcript, and API digests.",
		"exact lineage summary")
	var fallback: String = ui._summarize_answer_integrity({
		"status": "grounding_policy_fallback",
		"invocation_output_text_sha256": _sha256("Unsupported raw claim."),
		"transcript_text_sha256": digest,
		"delivery_text_sha256": digest,
	}, answer)
	_check(fallback.contains("raw inference differs (grounding_policy_fallback)"),
		"grounding fallback summary")
	var transcript_recall: String = ui._summarize_answer_integrity({
		"status": "prior_user_transcript_recall_output",
		"transcript_text_sha256": digest,
		"delivery_text_sha256": digest,
	}, answer)
	_check(transcript_recall == "Displayed answer matches transcript/API; raw inference digest unavailable.",
		"transcript-recall summary")
	var legacy: String = ui._summarize_answer_integrity({
		"status": "historical_lineage_unavailable",
		"transcript_text_sha256": digest,
		"delivery_text_sha256": digest,
	}, answer)
	_check(legacy.contains("raw inference digest unavailable"),
		"legacy raw digest summary")
	var mismatch: String = ui._summarize_answer_integrity({
		"status": "exact_invocation_output_match",
		"invocation_output_text_sha256": digest,
		"transcript_text_sha256": _sha256("Different transcript."),
		"delivery_text_sha256": digest,
	}, answer)
	_check(mismatch == "Displayed answer digest mismatch or lineage unavailable.",
		"transcript mismatch summary")
	ui.free()
	if not _probe_failures.is_empty():
		for failure in _probe_failures:
			push_error("Companion UI probe failed: " + failure)
		quit(1)
		return
	print("Godot companion chat UI probe passed.")
	quit(0)


func _sha256(text: String) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(text.to_utf8_buffer())
	return context.finish().hex_encode()


func _check(condition: bool, name: String) -> void:
	if condition:
		return
	_probe_failures.append(name)
