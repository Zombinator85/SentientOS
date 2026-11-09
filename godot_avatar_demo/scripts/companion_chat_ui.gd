extends Control
## Development-only text interface for the supervised loopback chat service.
## Screen observation is a one-message local OCR/vision opt-in; transcript retention stays off.

const API_BASE := "http://127.0.0.1:5000"
const MAX_VISIBLE_MESSAGES := 12
const CHAT_WINDOW_SIZE := Vector2i(520, 620)
const AVATAR_WINDOW_SIZE := Vector2i(140, 140)
const WINDOW_RESIZE_OFFSET := Vector2i(190, 220)
const CORNER_SNAP_RADIUS := 120.0
const CORNER_MARGIN := 12
const COMPACT_AVATAR_VISIBLE_BOUNDS := Rect2i(Vector2i(48, 16), Vector2i(44, 64))
const CHAT_AVATAR_POSITION := Vector3(0, 1.3, 0)
const CHAT_AVATAR_SCALE := Vector3(0.38, 0.38, 0.38)
const COMPACT_AVATAR_POSITION := Vector3(0, 0.65, 0)
const COMPACT_AVATAR_SCALE := Vector3(0.60, 0.60, 0.60)
const AVATAR_SCREEN_ANCHOR := Vector3(0, 1.49, 0)
const OVERLAY_POSITION_CONFIG := "user://companion_overlay.cfg"
const OVERLAY_POSITION_SECTION := "overlay"
const OVERLAY_POSITION_KEY := "compact_position"
const OVERLAY_POSITION_SAVE_DELAY := 0.75
const UI_PREFERENCES_SECTION := "preferences"
const SPEAK_REPLIES_KEY := "speak_replies"
const OBSERVE_GAME_SCREEN_KEY := "observe_game_screen"
const GLOBAL_HOTKEY_PORT := 60178
const GLOBAL_HOTKEY_TOGGLE_PACKET := "sentientos.toggle_chat.v1"
const OPAQUE_OBSERVATION_WINDOW_ARGUMENT := "--sentientos-opaque-observation-window"

var _request: HTTPRequest
var _runtime_status_request: HTTPRequest
var _runtime_status_timer: Timer
var _runtime_status_label: Label
var _runtime_status_in_flight := false
var _speech_output_request: HTTPRequest
var _speech_output_timer: Timer
var _speech_output_toggle: CheckBox
var _speech_output_status_label: Label
var _speech_output_in_flight := false
var _speech_output_enabled := false
var _speech_output_preference_enabled := true
var _screen_observation_preference_enabled := true
var _global_hotkey_server := UDPServer.new()
var _global_hotkey_helper_pid := 0
var _global_hotkey_started_msec := 0
var _global_hotkey_registered := false
var _speech_auto_enable_retry_after_msec := 0
var _last_timing_summary := ""
var _speech_output_requested_enabled := false
var _speech_output_action := ""
var _history: VBoxContainer
var _history_scroll: ScrollContainer
var _overlay_drag_handle: Label
var _chat_panel: PanelContainer
var _chat_visible := false
var _status_label: Label
var _avatar_node: Node3D
var _overlay_compact := false
var _compact_window_position := Vector2i.ZERO
var _has_compact_window_position := false
var _last_observed_window_position := Vector2i.ZERO
var _expanded_window_position := Vector2i.ZERO
var _compact_drag_button := MOUSE_BUTTON_NONE
var _compact_drag_moved := false
var _compact_drag_accumulated := Vector2.ZERO
var _position_save_elapsed := 0.0
var _session_status_label: Label
var _start_button: Button
var _resume_button: Button
var _message_input: LineEdit
var _send_button: Button
var _settings_button: Button
var _settings_panel: HBoxContainer
var _screen_observation_toggle: CheckBox
var _session_id := ""
var _last_completed_turn_id := ""
var _last_integrity_summary := ""
var _pending_action := ""
var _next_after_profile := ""
var _messages := PackedStringArray()
var _chat_request_started_usec := 0
var _first_ui_update_ms := -1
var _stream_client: HTTPClient
var _stream_request_sent := false
var _stream_seen_body := false
var _stream_response_code := 0
var _stream_buffer := ""
var _stream_error_body := PackedByteArray()
var _stream_reply_text := ""
var _stream_reply_message_index := -1
var _stream_request_body := ""
var _stream_user_message := ""
var _stream_recovery_attempt := 0
var _stream_recovery_timer: Timer


func _process(_delta: float) -> void:
	_track_compact_window_position(_delta)
	_poll_global_hotkey_bridge()
	if _stream_client == null:
		return
	var poll_error := _stream_client.poll()
	if poll_error != OK:
		_finish_stream_failure("The streaming connection failed (%s)." % error_string(poll_error))
		return
	var status := _stream_client.get_status()
	if status == HTTPClient.STATUS_CONNECTED and not _stream_request_sent:
		var headers := PackedStringArray([
			"Content-Type: application/json",
			"Accept: text/event-stream",
		])
		var error := _stream_client.request(HTTPClient.METHOD_POST, "/chat/stream",
			headers, _stream_request_body)
		if error != OK:
			_finish_stream_failure("The streaming chat request could not start (%s)." % error_string(error))
			return
		_stream_request_sent = true
	elif status == HTTPClient.STATUS_BODY:
		_stream_seen_body = true
		_stream_response_code = _stream_client.get_response_code()
		while _stream_client.get_status() == HTTPClient.STATUS_BODY:
			var chunk := _stream_client.read_response_body_chunk()
			if chunk.is_empty():
				break
			if _stream_response_code >= 400:
				_stream_error_body.append_array(chunk)
			else:
				_consume_stream_bytes(chunk)
				if _stream_client == null:
					return
	elif status in [HTTPClient.STATUS_CANT_RESOLVE, HTTPClient.STATUS_CANT_CONNECT,
		HTTPClient.STATUS_CONNECTION_ERROR, HTTPClient.STATUS_TLS_HANDSHAKE_ERROR]:
		_finish_stream_failure("The streaming connection could not be established.")
		return
	if _stream_client != null and _stream_seen_body and status in [
		HTTPClient.STATUS_CONNECTED, HTTPClient.STATUS_DISCONNECTED,
	]:
		_finish_stream_transport()


func _ready() -> void:
	_load_ui_preferences()
	_build_interface()
	_start_global_hotkey_bridge()
	var root_window := get_window()
	_apply_window_capture_mode(root_window, OS.get_cmdline_user_args())
	_restore_overlay_position(root_window)
	call_deferred("_apply_restored_overlay_position")
	_set_chat_visible(false)
	_request = HTTPRequest.new()
	_request.timeout = 120.0
	_request.use_threads = true
	add_child(_request)
	_request.request_completed.connect(_on_request_completed)
	_runtime_status_request = HTTPRequest.new()
	_runtime_status_request.timeout = 6.0
	_runtime_status_request.use_threads = true
	add_child(_runtime_status_request)
	_runtime_status_request.request_completed.connect(_on_runtime_status_completed)
	_speech_output_request = HTTPRequest.new()
	_speech_output_request.timeout = 10.0
	_speech_output_request.use_threads = true
	add_child(_speech_output_request)
	_speech_output_request.request_completed.connect(_on_speech_output_request_completed)
	_speech_output_timer = Timer.new()
	_speech_output_timer.wait_time = 5.0
	_speech_output_timer.timeout.connect(_refresh_speech_output_status)
	add_child(_speech_output_timer)
	_speech_output_timer.start()
	_stream_recovery_timer = Timer.new()
	_stream_recovery_timer.one_shot = true
	_stream_recovery_timer.timeout.connect(_request_stream_commit_recovery)
	add_child(_stream_recovery_timer)
	_runtime_status_timer = Timer.new()
	_runtime_status_timer.wait_time = 5.0
	_runtime_status_timer.timeout.connect(_refresh_runtime_status)
	add_child(_runtime_status_timer)
	_refresh_runtime_status()
	_runtime_status_timer.start()
	_update_session_status()


func _is_opaque_observation_window_requested(user_args: PackedStringArray) -> bool:
	return user_args.has(OPAQUE_OBSERVATION_WINDOW_ARGUMENT)


func _apply_window_capture_mode(root_window: Window, user_args: PackedStringArray) -> void:
	var opaque_observation_window := _is_opaque_observation_window_requested(user_args)
	var transparent_window := DisplayServer.is_window_transparency_available() \
		and not opaque_observation_window
	var background_color := Color(0, 0, 0, 0)
	if not transparent_window:
		background_color = Color(0.018, 0.027, 0.037, 1.0)
	RenderingServer.set_default_clear_color(background_color)
	if root_window == null:
		return
	root_window.transparent = transparent_window
	root_window.get_viewport().transparent_bg = transparent_window
	root_window.set_flag(Window.FLAG_TRANSPARENT, transparent_window)
	if not transparent_window:
		var world_environment := get_node_or_null("../../WorldEnvironment") as WorldEnvironment
		if world_environment != null and world_environment.environment != null:
			world_environment.environment.background_mode = Environment.BG_COLOR
			world_environment.environment.background_color = background_color


func _build_interface() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	var panel := PanelContainer.new()
	panel.name = "ChatPanel"
	_chat_panel = panel
	panel.visible = false
	panel.anchor_left = 0.025
	panel.anchor_top = 1.0
	panel.anchor_right = 0.975
	panel.anchor_bottom = 1.0
	panel.offset_top = -604.0
	panel.offset_bottom = -16.0
	var panel_style := StyleBoxFlat.new()
	panel_style.bg_color = Color(0.012, 0.022, 0.03, 0.985)
	panel_style.border_width_left = 1
	panel_style.border_width_top = 1
	panel_style.border_width_right = 1
	panel_style.border_width_bottom = 1
	panel_style.border_color = Color(0.22, 0.48, 0.58, 0.9)
	panel_style.content_margin_left = 12
	panel_style.content_margin_top = 10
	panel_style.content_margin_right = 12
	panel_style.content_margin_bottom = 10
	panel_style.corner_radius_top_left = 8
	panel_style.corner_radius_top_right = 8
	panel_style.corner_radius_bottom_left = 8
	panel_style.corner_radius_bottom_right = 8
	panel.add_theme_stylebox_override("panel", panel_style)
	add_child(panel)

	var layout := VBoxContainer.new()
	layout.add_theme_constant_override("separation", 8)
	panel.add_child(layout)
	var drag_row := HBoxContainer.new()
	drag_row.custom_minimum_size.y = 22
	layout.add_child(drag_row)
	_overlay_drag_handle = Label.new()
	_overlay_drag_handle.name = "OverlayDragHandle"
	_overlay_drag_handle.text = "⠿  SentientOS  ·  drag to move"
	_overlay_drag_handle.tooltip_text = "Ctrl+Shift+Space opens or hides chat globally. Drag this handle to move the companion."
	_overlay_drag_handle.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_overlay_drag_handle.mouse_filter = Control.MOUSE_FILTER_STOP
	_overlay_drag_handle.gui_input.connect(_on_overlay_drag_handle_input)
	_overlay_drag_handle.add_theme_font_size_override("font_size", 12)
	drag_row.add_child(_overlay_drag_handle)
	var close_button := Button.new()
	close_button.name = "CloseChat"
	close_button.text = "×"
	close_button.tooltip_text = "Hide chat (Ctrl+Shift+Space)"
	close_button.pressed.connect(_toggle_chat_visibility)
	drag_row.add_child(close_button)
	_history_scroll = ScrollContainer.new()
	_history_scroll.name = "ConversationScroll"
	_history_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_history_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	layout.add_child(_history_scroll)
	_history = VBoxContainer.new()
	_history.name = "Conversation"
	_history.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_history.add_theme_constant_override("separation", 8)
	_history_scroll.add_child(_history)
	_session_status_label = Label.new()
	_session_status_label.name = "ConversationSessionStatus"
	_session_status_label.text = "No conversation selected."
	_session_status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_session_status_label.add_theme_font_size_override("font_size", 12)
	_session_status_label.autowrap_mode = TextServer.AUTOWRAP_OFF
	layout.add_child(_session_status_label)
	_runtime_status_label = Label.new()
	_runtime_status_label.name = "RuntimeStatus"
	_runtime_status_label.text = "Checking local runtime and model residency…"
	_runtime_status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_runtime_status_label.add_theme_font_size_override("font_size", 12)
	_runtime_status_label.autowrap_mode = TextServer.AUTOWRAP_OFF
	layout.add_child(_runtime_status_label)
	var action_row := HBoxContainer.new()
	action_row.add_theme_constant_override("separation", 6)
	layout.add_child(action_row)
	_start_button = Button.new()
	_start_button.text = "New chat"
	_start_button.pressed.connect(_start_chat)
	action_row.add_child(_start_button)
	_resume_button = Button.new()
	_resume_button.text = "Resume latest"
	_resume_button.pressed.connect(_resume_chat)
	action_row.add_child(_resume_button)
	_settings_button = Button.new()
	_settings_button.name = "ConversationSettings"
	_settings_button.text = "Settings"
	_settings_button.toggle_mode = true
	_settings_button.tooltip_text = "Show persistent voice and game-screen preferences."
	_settings_button.toggled.connect(_on_settings_toggled)
	action_row.add_child(_settings_button)

	_settings_panel = HBoxContainer.new()
	_settings_panel.name = "PersistentPreferences"
	_settings_panel.add_theme_constant_override("separation", 8)
	_settings_panel.visible = false
	layout.add_child(_settings_panel)
	_speech_output_toggle = CheckBox.new()
	_speech_output_toggle.name = "SpeakRepliesWithLocalVoice"
	_speech_output_toggle.text = "Voice"
	_speech_output_toggle.tooltip_text = "Speak SentientOS replies with the local system voice. This preference is saved on this machine and reapplied to conversations."
	_speech_output_toggle.button_pressed = _speech_output_preference_enabled
	_speech_output_toggle.disabled = true
	_speech_output_toggle.toggled.connect(_on_speech_output_toggled)
	_settings_panel.add_child(_speech_output_toggle)
	_speech_output_status_label = Label.new()
	_speech_output_status_label.name = "LocalSpeechStatus"
	_speech_output_status_label.text = "On" if _speech_output_preference_enabled else "Off"
	_speech_output_status_label.custom_minimum_size.x = 110
	_speech_output_status_label.add_theme_font_size_override("font_size", 12)
	_settings_panel.add_child(_speech_output_status_label)
	_screen_observation_toggle = CheckBox.new()
	_screen_observation_toggle.name = "ObserveGameScreen"
	_screen_observation_toggle.text = "Game screen"
	_screen_observation_toggle.tooltip_text = "This saved preference requests one fresh frame from the allowlisted foreground game with each message. OCR and optional visual summary stay local; frames are discarded. No background capture runs."
	_screen_observation_toggle.button_pressed = _screen_observation_preference_enabled
	_screen_observation_toggle.disabled = true
	_screen_observation_toggle.add_theme_font_size_override("font_size", 14)
	_screen_observation_toggle.toggled.connect(_on_screen_observation_toggled)
	_settings_panel.add_child(_screen_observation_toggle)
	var compose_row := HBoxContainer.new()
	compose_row.add_theme_constant_override("separation", 6)
	layout.add_child(compose_row)
	_message_input = LineEdit.new()
	_message_input.placeholder_text = "Message SentientOS…"
	_message_input.custom_minimum_size.y = 44
	_message_input.add_theme_font_size_override("font_size", 16)
	_message_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_message_input.editable = false
	_message_input.text_submitted.connect(_send_message)
	compose_row.add_child(_message_input)
	_send_button = Button.new()
	_send_button.text = "Send"
	_send_button.custom_minimum_size = Vector2(76, 44)
	_send_button.disabled = true
	_send_button.pressed.connect(_send_message.bind(""))
	compose_row.add_child(_send_button)
	_status_label = get_node_or_null("../StatusLabel") as Label
	_avatar_node = get_node_or_null("../../Avatar") as Node3D


func _set_chat_visible(visible: bool) -> void:
	_chat_visible = visible
	if _chat_panel != null:
		_chat_panel.visible = visible
	if _status_label != null:
		_status_label.visible = false
	var window := get_window()
	if window == null:
		return
	window.mouse_passthrough_polygon = PackedVector2Array()
	if visible and _overlay_compact:
		_compact_window_position = window.position
		_has_compact_window_position = true
		_save_overlay_position()
		var preserve_avatar_anchor := _avatar_node != null and window.get_viewport().get_camera_3d() != null
		var avatar_screen_position := Vector2.ZERO
		if preserve_avatar_anchor:
			avatar_screen_position = _capture_avatar_screen_position(window)
		window.position = _compact_window_position - WINDOW_RESIZE_OFFSET
		window.size = CHAT_WINDOW_SIZE
		if _avatar_node != null:
			_avatar_node.position = CHAT_AVATAR_POSITION
			_avatar_node.scale = CHAT_AVATAR_SCALE
		_overlay_compact = false
		_keep_window_onscreen(window)
		if preserve_avatar_anchor:
			_restore_avatar_screen_position(window, avatar_screen_position)
		_expanded_window_position = window.position
		_last_observed_window_position = window.position
		_position_save_elapsed = 0.0
	elif not visible and not _overlay_compact:
		_sync_compact_position_from_expanded_window(window)
		window.position = _compact_window_position if _has_compact_window_position \
			else window.position + WINDOW_RESIZE_OFFSET
		window.size = AVATAR_WINDOW_SIZE
		if _avatar_node != null:
			_avatar_node.position = COMPACT_AVATAR_POSITION
			_avatar_node.scale = COMPACT_AVATAR_SCALE
		_overlay_compact = true
		_keep_window_onscreen(window)
		_compact_window_position = window.position
		_has_compact_window_position = true
		_last_observed_window_position = window.position
		_save_overlay_position()
	elif not visible and _overlay_compact:
		_compact_window_position = window.position
		_has_compact_window_position = true
		_save_overlay_position()


func _keep_window_onscreen(window: Window) -> void:
	var screen := DisplayServer.window_get_current_screen()
	var usable_area := DisplayServer.screen_get_usable_rect(screen)
	window.position = _clamped_compact_position(window.position, usable_area) \
		if _overlay_compact else _clamped_window_position(window.position, window.size, usable_area)
	if _overlay_compact:
		_compact_window_position = window.position
		_has_compact_window_position = true
		_last_observed_window_position = window.position


func _capture_avatar_screen_position(window: Window) -> Vector2:
	var camera := window.get_viewport().get_camera_3d()
	var avatar_anchor := _avatar_node.to_global(AVATAR_SCREEN_ANCHOR)
	return Vector2(window.position) + camera.unproject_position(avatar_anchor)


func _restore_avatar_screen_position(window: Window, screen_position: Vector2) -> void:
	var camera := window.get_viewport().get_camera_3d()
	var avatar_anchor := _avatar_node.to_global(AVATAR_SCREEN_ANCHOR)
	var camera_depth := -camera.to_local(avatar_anchor).z
	var viewport_position := screen_position - Vector2(window.position)
	var target_anchor := camera.project_position(viewport_position, camera_depth)
	var anchor_offset := avatar_anchor - _avatar_node.global_position
	_avatar_node.global_position = target_anchor - anchor_offset


func _apply_restored_overlay_position() -> void:
	await get_tree().process_frame
	var window := get_window()
	if window == null or not _overlay_compact:
		return
	var usable_area := DisplayServer.screen_get_usable_rect(DisplayServer.window_get_current_screen())
	window.position = _clamped_compact_position(_compact_window_position, usable_area)
	_compact_window_position = window.position
	_last_observed_window_position = window.position
	_save_overlay_position()


func _overlay_config_path() -> String:
	var persistent_path := OS.get_environment("SENTIENTOS_OVERLAY_CONFIG_PATH")
	return persistent_path if not persistent_path.is_empty() else OVERLAY_POSITION_CONFIG


func _restore_overlay_position(window: Window) -> void:
	if window == null:
		return
	var config := ConfigFile.new()
	if config.load(_overlay_config_path()) == OK:
		var saved: Variant = config.get_value(OVERLAY_POSITION_SECTION, OVERLAY_POSITION_KEY, null)
		if saved is Vector2i:
			_compact_window_position = saved
			_has_compact_window_position = true
	if not _has_compact_window_position:
		var usable_area := DisplayServer.screen_get_usable_rect(DisplayServer.window_get_current_screen())
		_compact_window_position = _default_overlay_position(usable_area)
		_has_compact_window_position = true
	window.size = AVATAR_WINDOW_SIZE
	_overlay_compact = true
	window.position = _clamped_compact_position(
		_compact_window_position,
		DisplayServer.screen_get_usable_rect(DisplayServer.window_get_current_screen()))
	_compact_window_position = window.position
	_last_observed_window_position = window.position
	_save_overlay_position()


func _default_overlay_position(usable_area: Rect2i) -> Vector2i:
	return _corner_positions(usable_area)[3]


func _corner_positions(usable_area: Rect2i) -> Array[Vector2i]:
	var visible_end := COMPACT_AVATAR_VISIBLE_BOUNDS.position + COMPACT_AVATAR_VISIBLE_BOUNDS.size
	var area_end := usable_area.position + usable_area.size
	var left := usable_area.position.x + CORNER_MARGIN - COMPACT_AVATAR_VISIBLE_BOUNDS.position.x
	var right := area_end.x - CORNER_MARGIN - visible_end.x
	var top := usable_area.position.y + CORNER_MARGIN - COMPACT_AVATAR_VISIBLE_BOUNDS.position.y
	var bottom := area_end.y - CORNER_MARGIN - visible_end.y
	return [Vector2i(left, top), Vector2i(right, top), Vector2i(left, bottom), Vector2i(right, bottom)]


func _clamped_compact_position(position: Vector2i, usable_area: Rect2i) -> Vector2i:
	var visible_end := COMPACT_AVATAR_VISIBLE_BOUNDS.position + COMPACT_AVATAR_VISIBLE_BOUNDS.size
	var area_end := usable_area.position + usable_area.size
	var minimum := usable_area.position + Vector2i(CORNER_MARGIN, CORNER_MARGIN) \
		- COMPACT_AVATAR_VISIBLE_BOUNDS.position
	var maximum := area_end - Vector2i(CORNER_MARGIN, CORNER_MARGIN) - visible_end
	return Vector2i(clampi(position.x, minimum.x, maximum.x), clampi(position.y, minimum.y, maximum.y))


func _snap_compact_position_to_nearest_corner(position: Vector2i, usable_area: Rect2i) -> Vector2i:
	var nearest := position
	var nearest_distance := CORNER_SNAP_RADIUS
	for corner in _corner_positions(usable_area):
		var distance := Vector2(position).distance_to(Vector2(corner))
		if distance <= nearest_distance:
			nearest = corner
			nearest_distance = distance
	return nearest


func _track_compact_window_position(delta: float) -> void:
	var window := get_window()
	if window == null:
		_position_save_elapsed = 0.0
		return
	if window.position != _last_observed_window_position:
		_last_observed_window_position = window.position
		if _overlay_compact:
			_compact_window_position = window.position
			_has_compact_window_position = true
		elif _chat_visible:
			_sync_compact_position_from_expanded_window(window)
		_position_save_elapsed = 0.0
		return
	if _position_save_elapsed >= 0.0:
		_position_save_elapsed += delta
		if _position_save_elapsed >= OVERLAY_POSITION_SAVE_DELAY:
			_save_overlay_position()
			_position_save_elapsed = -1.0


func _compact_position_from_expanded_window(expanded_position: Vector2i, usable_area: Rect2i) -> Vector2i:
	return _clamped_compact_position(expanded_position + WINDOW_RESIZE_OFFSET, usable_area)


func _sync_compact_position_from_expanded_window(window: Window) -> void:
	if window.position == _expanded_window_position:
		return
	var usable_area := DisplayServer.screen_get_usable_rect(DisplayServer.window_get_current_screen())
	_compact_window_position = _compact_position_from_expanded_window(window.position, usable_area)
	_has_compact_window_position = true
	_expanded_window_position = window.position
	_save_overlay_position()


func _save_overlay_position() -> void:
	if not _has_compact_window_position:
		return
	var config := ConfigFile.new()
	config.load(_overlay_config_path())
	config.set_value(OVERLAY_POSITION_SECTION, OVERLAY_POSITION_KEY, _compact_window_position)
	config.save(_overlay_config_path())


func _load_ui_preferences() -> void:
	var config := ConfigFile.new()
	config.load(_overlay_config_path())
	_load_preferences_from_config(config)
	_write_preferences_to_config(config)
	config.save(_overlay_config_path())


func _load_preferences_from_config(config: ConfigFile) -> void:
	var speech_value: Variant = config.get_value(
		UI_PREFERENCES_SECTION, SPEAK_REPLIES_KEY, true)
	var screen_value: Variant = config.get_value(
		UI_PREFERENCES_SECTION, OBSERVE_GAME_SCREEN_KEY, true)
	_speech_output_preference_enabled = speech_value is bool and speech_value
	_screen_observation_preference_enabled = screen_value is bool and screen_value


func _write_preferences_to_config(config: ConfigFile) -> void:
	config.set_value(UI_PREFERENCES_SECTION, SPEAK_REPLIES_KEY,
		_speech_output_preference_enabled)
	config.set_value(UI_PREFERENCES_SECTION, OBSERVE_GAME_SCREEN_KEY,
		_screen_observation_preference_enabled)


func _save_ui_preferences() -> void:
	var config := ConfigFile.new()
	config.load(_overlay_config_path())
	_write_preferences_to_config(config)
	config.save(_overlay_config_path())


func _clamped_window_position(position: Vector2i, size: Vector2i, usable_area: Rect2i) -> Vector2i:
	var usable_end := usable_area.position + usable_area.size
	var maximum := Vector2i(
		max(usable_area.position.x, usable_end.x - size.x),
		max(usable_area.position.y, usable_end.y - size.y),
	)
	return Vector2i(
		clampi(position.x, usable_area.position.x, maximum.x),
		clampi(position.y, usable_area.position.y, maximum.y),
	)


func _toggle_chat_visibility() -> void:
	_set_chat_visible(not _chat_visible)


func _start_global_hotkey_bridge() -> void:
	if OS.get_name() != "Windows":
		return
	var listen_error := _global_hotkey_server.listen(GLOBAL_HOTKEY_PORT, "127.0.0.1")
	if listen_error != OK:
		_set_global_hotkey_status("Could not listen for the system shortcut (%s)." % error_string(listen_error), false)
		return
	var helper_path := ProjectSettings.globalize_path("res://scripts/companion_global_hotkey.ps1")
	if not FileAccess.file_exists(helper_path):
		_set_global_hotkey_status("The system shortcut helper is missing.", false)
		return
	var arguments := PackedStringArray([
		"-NoLogo", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
		"-ExecutionPolicy", "Bypass", "-File", helper_path,
		"-Port", str(GLOBAL_HOTKEY_PORT),
	])
	_global_hotkey_helper_pid = OS.create_process("powershell.exe", arguments, false)
	if _global_hotkey_helper_pid <= 0:
		_set_global_hotkey_status("Could not start the system shortcut helper.", false)
		return
	_global_hotkey_started_msec = Time.get_ticks_msec()


func _poll_global_hotkey_bridge() -> void:
	if _global_hotkey_server.is_listening():
		_global_hotkey_server.poll()
		while _global_hotkey_server.is_connection_available():
			var peer := _global_hotkey_server.take_connection()
			while peer.get_available_packet_count() > 0:
				_handle_global_hotkey_packet(peer.get_packet().get_string_from_utf8())
	if not _global_hotkey_registered and _global_hotkey_started_msec > 0 \
		and Time.get_ticks_msec() - _global_hotkey_started_msec > 5000:
		_global_hotkey_started_msec = 0
		_set_global_hotkey_status("No system shortcut registration response; click the avatar to open chat.", false)


func _handle_global_hotkey_packet(packet: String) -> void:
	if packet == "registered":
		_global_hotkey_registered = true
		_global_hotkey_started_msec = 0
		if _overlay_drag_handle != null:
			_overlay_drag_handle.tooltip_text = "Ctrl+Shift+Space opens or hides chat globally. Drag this handle to move the companion."
	elif packet.begins_with("registration_failed:"):
		_global_hotkey_started_msec = 0
		_set_global_hotkey_status("System shortcut registration failed (%s); click the avatar to open chat." % packet.trim_prefix("registration_failed:"), false)
	elif packet == GLOBAL_HOTKEY_TOGGLE_PACKET:
		_toggle_chat_visibility()


func _set_global_hotkey_status(message: String, registered: bool) -> void:
	_global_hotkey_registered = registered
	if _overlay_drag_handle != null:
		_overlay_drag_handle.tooltip_text = message


func _exit_tree() -> void:
	if _global_hotkey_helper_pid > 0:
		OS.kill(_global_hotkey_helper_pid)
		_global_hotkey_helper_pid = 0
	_global_hotkey_server.stop()


func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo \
		and event.keycode == KEY_SPACE and event.ctrl_pressed and event.shift_pressed:
		_toggle_chat_visibility()
		get_viewport().set_input_as_handled()
	elif not _chat_visible and event is InputEventMouseButton:
		if event.pressed and event.button_index in [MOUSE_BUTTON_LEFT, MOUSE_BUTTON_RIGHT]:
			_compact_drag_button = event.button_index
			_compact_drag_moved = false
			_compact_drag_accumulated = Vector2.ZERO
			get_viewport().set_input_as_handled()
		elif not event.pressed and event.button_index == _compact_drag_button:
			var open_chat: bool = event.button_index == MOUSE_BUTTON_LEFT and not _compact_drag_moved
			_compact_drag_button = MOUSE_BUTTON_NONE
			if _compact_drag_moved:
				var window := get_window()
				var usable_area := DisplayServer.screen_get_usable_rect(DisplayServer.window_get_current_screen())
				window.position = _snap_compact_position_to_nearest_corner(window.position, usable_area)
				_compact_window_position = window.position
				_has_compact_window_position = true
				_last_observed_window_position = window.position
				_save_overlay_position()
			elif open_chat:
				_set_chat_visible(true)
			get_viewport().set_input_as_handled()
	elif not _chat_visible and event is InputEventMouseMotion \
		and _compact_drag_button != MOUSE_BUTTON_NONE:
		var movement: Vector2 = event.relative
		if not _compact_drag_moved:
			_compact_drag_accumulated += movement
			if _compact_drag_accumulated.length() < 4.0:
				get_viewport().set_input_as_handled()
				return
			movement = _compact_drag_accumulated
			_compact_drag_moved = true
		var window := get_window()
		var usable_area := DisplayServer.screen_get_usable_rect(DisplayServer.window_get_current_screen())
		window.position = _clamped_compact_position(
			window.position + Vector2i(movement.round()), usable_area)
		_compact_window_position = window.position
		_has_compact_window_position = true
		_last_observed_window_position = window.position
		get_viewport().set_input_as_handled()


func _refresh_runtime_status() -> void:
	if _runtime_status_in_flight:
		return
	_runtime_status_in_flight = true
	var error := _runtime_status_request.request(API_BASE + "/runtime-status")
	if error != OK:
		_runtime_status_in_flight = false
		_runtime_status_label.text = "Local runtime status unavailable."


func _on_runtime_status_completed(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	_runtime_status_in_flight = false
	if result != HTTPRequest.RESULT_SUCCESS or response_code < 200 or response_code >= 300:
		_runtime_status_label.text = "Local runtime status unavailable."
		return
	var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
	if not parsed is Dictionary:
		_runtime_status_label.text = "Local runtime status unavailable."
		return
	if parsed.get("posture") != "development_only" or parsed.get("status") != "running":
		_runtime_status_label.text = "Local chat runtime unavailable."
		return
	var residency: Variant = parsed.get("model_residency", {})
	var model_status := "local model residency unavailable"
	if residency is Dictionary:
		match residency.get("status", "unavailable"):
			"resident":
				model_status = "local model loaded"
			"unloaded":
				model_status = "local model unloaded"
			"operation_in_progress":
				model_status = "model transition or inference in progress"
			"not_applicable":
				model_status = "model residency not applicable"
	var workload := str(parsed.get("effective_workload_mode", "unknown"))
	_runtime_status_label.text = "%s · %s · local" % [workload.capitalize(), model_status.replace("local ", "")]


func _refresh_speech_output_status() -> void:
	if _session_id.is_empty() or _speech_output_in_flight:
		return
	_speech_output_in_flight = true
	_speech_output_action = "status"
	var error := _speech_output_request.request(
		API_BASE + "/speech-output?session_id=" + _session_id)
	if error != OK:
		_speech_output_in_flight = false
		_speech_output_toggle.disabled = true
		_speech_output_status_label.text = "Unavailable"
		_speech_output_status_label.tooltip_text = "Local speech status unavailable."


func _on_speech_output_toggled(enabled: bool) -> void:
	_speech_output_preference_enabled = enabled
	_save_ui_preferences()
	_speech_output_status_label.text = "On" if enabled else "Off"
	if _session_id.is_empty() or _speech_output_in_flight:
		return
	_request_speech_output_change(enabled, "set")


func _on_screen_observation_toggled(enabled: bool) -> void:
	_screen_observation_preference_enabled = enabled
	_save_ui_preferences()


func _request_speech_output_change(enabled: bool, action: String) -> void:
	if _session_id.is_empty() or _speech_output_in_flight:
		return
	_speech_output_in_flight = true
	_speech_output_action = action
	_speech_output_requested_enabled = enabled
	_speech_output_toggle.disabled = true
	_speech_output_status_label.text = "…"
	var headers := PackedStringArray(["Content-Type: application/json"])
	var body := JSON.stringify({"session_id": _session_id, "enabled": enabled})
	var error := _speech_output_request.request(
		API_BASE + "/speech-output", headers, HTTPClient.METHOD_POST, body)
	if error != OK:
		_speech_output_in_flight = false
		_speech_output_status_label.text = "Unavailable"
		_speech_output_status_label.tooltip_text = "Could not update local voice approval."
		_speech_output_timer.start()


func _on_speech_output_request_completed(result: int, response_code: int,
		_headers: PackedStringArray, body: PackedByteArray) -> void:
	var action := _speech_output_action
	_speech_output_action = ""
	_speech_output_in_flight = false
	if result != HTTPRequest.RESULT_SUCCESS or response_code < 200 or response_code >= 300:
		_speech_output_status_label.text = "Unavailable"
		_speech_output_status_label.tooltip_text = "Local voice status or approval request failed."
		_speech_output_toggle.disabled = true
		return
	var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
	if not parsed is Dictionary:
		_speech_output_status_label.text = "Unavailable"
		_speech_output_status_label.tooltip_text = "Local voice status response was invalid."
		_speech_output_toggle.disabled = true
		return
	if action in ["set", "auto_enable"]:
		_speech_output_enabled = parsed.get("enabled", false) == true
		_speech_output_toggle.set_pressed_no_signal(_speech_output_preference_enabled)
		_speech_output_toggle.disabled = false
		if _speech_output_requested_enabled and not _speech_output_enabled:
			var reason := str(parsed.get("reason", "approval_not_granted"))
			_speech_output_status_label.text = "Needs approval"
			_speech_output_status_label.tooltip_text = "Local voice approval was not granted (%s)." % reason
			_speech_output_timer.start()
			return
		_speech_output_status_label.text = "On" if _speech_output_enabled else "Off"
		_refresh_speech_output_status()
		return

	var configured: bool = parsed.get("configured", false) == true
	var backend_available: bool = parsed.get("backend_available", false) == true
	_speech_output_enabled = parsed.get("enabled", false) == true
	_speech_output_toggle.set_pressed_no_signal(_speech_output_preference_enabled)
	_speech_output_toggle.disabled = not configured or not backend_available
	if not configured:
		_speech_output_status_label.text = "Unavailable"
		_speech_output_status_label.tooltip_text = "Local voice is not configured for this server."
	elif not backend_available:
		_speech_output_status_label.text = "Unavailable"
		_speech_output_status_label.tooltip_text = "Local system voice backend is unavailable."
	elif _speech_output_preference_enabled and not _speech_output_enabled:
		_speech_output_status_label.text = "On…"
		_speech_output_status_label.tooltip_text = "Reapplying the saved local voice preference to this conversation."
		var now_msec := Time.get_ticks_msec()
		if now_msec >= _speech_auto_enable_retry_after_msec:
			_speech_auto_enable_retry_after_msec = now_msec + 60000
			_request_speech_output_change(true, "auto_enable")
	else:
		var playback := str(parsed.get("playback_status", "unknown"))
		var failure_code := str(parsed.get("playback_failure_code", ""))
		_speech_output_status_label.text = "On · %s" % playback if _speech_output_enabled else "Off"
		_speech_output_status_label.tooltip_text = "Local voice approval: %s; playback: %s%s" % [
			"active" if _speech_output_enabled else "off", playback,
			(" · " + failure_code) if failure_code.is_valid_identifier() else ""]


func _start_chat() -> void:
	_select_profile_then("create_session")


func _resume_chat() -> void:
	_select_profile_then("load_sessions")


func _select_profile_then(next_action: String) -> void:
	if not _pending_action.is_empty():
		return
	_next_after_profile = next_action
	_pending_action = "read_workload_mode"
	_start_button.disabled = true
	_resume_button.disabled = true
	_start_button.text = "Selecting game-aware profile…"
	var error := _request.request(API_BASE + "/workload-mode")
	if error != OK:
		_fail_request("Could not read the game profile configuration (%s)." % error_string(error))


func _send_message(submitted_text: String = "") -> void:
	if _session_id.is_empty() or not _pending_action.is_empty():
		return
	var message := submitted_text if not submitted_text.is_empty() else _message_input.text
	message = message.strip_edges()
	if message.is_empty():
		return
	var observe_screen := _screen_observation_toggle.button_pressed
	_append_message("You", message)
	_message_input.clear()
	_message_input.editable = false
	_send_button.disabled = true
	_pending_action = "chat"
	_chat_request_started_usec = Time.get_ticks_usec()
	_first_ui_update_ms = -1
	var request_body := JSON.stringify({
		"message": message,
		"session_id": _session_id,
		"retain": false,
		"request_id": "godot-ui-%d-%d" % [Time.get_ticks_usec(), randi()],
		"observe_screen": observe_screen,
	})
	_stream_request_body = request_body
	_stream_client = HTTPClient.new()
	_stream_request_sent = false
	_stream_seen_body = false
	_stream_response_code = 0
	_stream_buffer = ""
	_stream_error_body = PackedByteArray()
	_stream_reply_text = ""
	_stream_reply_message_index = -1
	_stream_user_message = message
	_stream_recovery_attempt = 0
	var error := _stream_client.connect_to_host("127.0.0.1", 5000)
	if error != OK:
		_finish_stream_failure("The streaming connection could not start (%s)." % error_string(error))


func _on_request_completed(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	if _pending_action == "recover_stream_commit":
		_handle_stream_commit_recovery(result, response_code, body)
		return
	var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
	var array_response_allowed := _pending_action == "load_sessions" and parsed is Array
	if result != HTTPRequest.RESULT_SUCCESS or response_code < 200 or response_code >= 300 or (not parsed is Dictionary and not array_response_allowed):
		var detail := "SentientOS request failed (HTTP %d, result %d)." % [response_code, result]
		if parsed is Dictionary and parsed.get("detail") is String:
			detail = "SentientOS: " + str(parsed["detail"])
		_fail_request(detail)
		return
	match _pending_action:
		"read_workload_mode":
			var process_names: Variant = parsed.get("configured_game_process_names", [])
			if not process_names is Array or process_names.is_empty():
				_fail_request("No game process allowlist is configured for automatic mode.")
				return
			_pending_action = "set_workload_mode"
			var headers := PackedStringArray(["Content-Type: application/json"])
			var body_text := JSON.stringify({
				"mode": "automatic",
				"game_process_names": process_names,
			})
			var error := _request.request(API_BASE + "/workload-mode", headers, HTTPClient.METHOD_POST, body_text)
			if error != OK:
				_fail_request("Could not select the automatic profile (%s)." % error_string(error))
		"set_workload_mode":
			if parsed.get("effective_mode") not in ["gaming", "normal"]:
				_fail_request("SentientOS did not confirm a workload profile.")
				return
			if _next_after_profile == "load_sessions":
				_pending_action = "load_sessions"
				var error := _request.request(API_BASE + "/sessions")
				if error != OK:
					_fail_request("Could not list recent conversations (%s)." % error_string(error))
			else:
				_pending_action = "create_session"
				var error := _request.request(API_BASE + "/sessions", PackedStringArray(), HTTPClient.METHOD_POST, "")
				if error != OK:
					_fail_request("Could not create a conversation (%s)." % error_string(error))
		"load_sessions":
			var sessions: Array = parsed
			var recent: Dictionary = {}
			for entry in sessions:
				if entry is Dictionary and entry.get("lifecycle_state") == "active":
					recent = entry
					break
			_session_id = str(recent.get("session_id", ""))
			_last_completed_turn_id = ""
			_last_integrity_summary = ""
			_last_timing_summary = ""
			_update_session_status()
			if _session_id.is_empty():
				_fail_request("There is no recent active conversation to resume.")
				return
			_pending_action = "load_turns"
			var error := _request.request(API_BASE + "/sessions/" + _session_id + "/turns")
			if error != OK:
				_fail_request("Could not load the recent conversation (%s)." % error_string(error))
		"load_turns":
			var turns: Variant = parsed.get("turns", [])
			if not turns is Array:
				_fail_request("The recent conversation transcript was unavailable.")
				return
			_messages.clear()
			for turn in turns:
				if turn is Dictionary:
					var role := str(turn.get("role", ""))
					var text := str(turn.get("text", ""))
					if role == "user":
						_append_message("You", text)
					elif role == "assistant":
						_append_message("SentientOS", text)
						var turn_id := str(turn.get("turn_id", ""))
						if not turn_id.is_empty():
							_last_completed_turn_id = turn_id
						var diagnostics_value: Variant = turn.get("response_diagnostics", {})
						_last_integrity_summary = _summarize_answer_integrity(
							diagnostics_value, text)
			_update_session_status()
			_pending_action = "enable_avatar"
			var output_body := JSON.stringify({"session_id": _session_id, "enabled": true})
			var headers := PackedStringArray(["Content-Type: application/json"])
			var error := _request.request(API_BASE + "/avatar-output", headers, HTTPClient.METHOD_POST, output_body)
			if error != OK:
				_fail_request("The visual companion connection could not resume (%s)." % error_string(error))
		"create_session":
			_session_id = str(parsed.get("session_id", ""))
			_last_completed_turn_id = ""
			_last_integrity_summary = ""
			_last_timing_summary = ""
			_update_session_status()
			if _session_id.is_empty():
				_fail_request("SentientOS did not return a conversation session.")
				return
			_messages.clear()
			_pending_action = "enable_avatar"
			var output_body := JSON.stringify({"session_id": _session_id, "enabled": true})
			var headers := PackedStringArray(["Content-Type: application/json"])
			var error := _request.request(API_BASE + "/avatar-output", headers, HTTPClient.METHOD_POST, output_body)
			if error != OK:
				_fail_request("The visual companion connection could not start (%s)." % error_string(error))
		"enable_avatar":
			_pending_action = ""
			_next_after_profile = ""
			_update_session_status()
			_start_button.text = "New chat"
			_resume_button.text = "Resumed"
			_start_button.disabled = false
			_resume_button.disabled = true
			_screen_observation_toggle.disabled = false
			_speech_output_toggle.set_pressed_no_signal(_speech_output_preference_enabled)
			_refresh_speech_output_status()
			_message_input.editable = true
			_send_button.disabled = false
			_message_input.grab_focus()
			_session_status_label.text = "Conversation ready"
		"chat":
			_finish_non_streamed_chat(parsed)
		_:
			_fail_request("The local chat service returned an unexpected response.")


func _consume_stream_bytes(chunk: PackedByteArray) -> void:
	_stream_buffer += chunk.get_string_from_utf8().replace("\r\n", "\n")
	while true:
		var separator := _stream_buffer.find("\n\n")
		if separator < 0:
			return
		var event_text := _stream_buffer.substr(0, separator)
		_stream_buffer = _stream_buffer.substr(separator + 2)
		_consume_stream_event_text(event_text)
		if _stream_client == null:
			return


func _consume_stream_event_text(event_text: String) -> void:
	for line in event_text.split("\n"):
		if not line.begins_with("data:"):
			continue
		var parsed: Variant = JSON.parse_string(line.substr(5).strip_edges())
		if parsed is Dictionary:
			_handle_stream_event(parsed)


func _handle_stream_event(event: Dictionary) -> void:
	match str(event.get("type", "")):
		"delta":
			var text := str(event.get("text", ""))
			if text.is_empty():
				return
			var first_ui_update := _stream_reply_message_index < 0
			if _stream_reply_message_index < 0:
				_stream_reply_message_index = _messages.size()
				_messages.append("SentientOS: ")
			_stream_reply_text += text
			_messages[_stream_reply_message_index] = "SentientOS: " + _stream_reply_text
			_render_history()
			if first_ui_update and _chat_request_started_usec > 0:
				_first_ui_update_ms = int((Time.get_ticks_usec() - _chat_request_started_usec) / 1000)
		"complete":
			var response_value: Variant = event.get("response", {})
			var response: Dictionary = response_value if response_value is Dictionary else {}
			var answer := str(response.get("response", _stream_reply_text))
			_last_completed_turn_id = str(response.get("turn_id", ""))
			_last_integrity_summary = _summarize_answer_integrity(
				response.get("response_diagnostics", {}), answer)
			_update_session_status()
			var first_ui_update := _stream_reply_message_index < 0
			if _stream_reply_message_index < 0:
				_stream_reply_message_index = _messages.size()
				_messages.append("")
			_stream_reply_text = answer
			_messages[_stream_reply_message_index] = "SentientOS: " + answer
			_render_history()
			if first_ui_update and _chat_request_started_usec > 0:
				_first_ui_update_ms = int((Time.get_ticks_usec() - _chat_request_started_usec) / 1000)
			var context_value: Variant = response.get("context", {})
			var context: Dictionary = context_value if context_value is Dictionary else {}
			var timing_value: Variant = context.get("inference_timing", {})
			var round_trip_ms := 0
			if _chat_request_started_usec > 0:
				round_trip_ms = int((Time.get_ticks_usec() - _chat_request_started_usec) / 1000)
			if timing_value is Dictionary:
				var timing_summary := _format_inference_timing(
					timing_value, round_trip_ms, _first_ui_update_ms)
				if not timing_summary.is_empty():
					_last_timing_summary = timing_summary
					_update_session_status()
			_finish_stream_success()
		"error":
			var code := str(event.get("code", "unknown"))
			if code == "screen_observation_failed":
				var failure_code := str(event.get("failure_code", ""))
				var guidance := "Check the Game screen setting, foreground game, and local capture status."
				if failure_code == "screen_observation_consent_expired":
					guidance = "Local screen permission expired. Renew the local game-capture session."
				elif failure_code == "game_screen_foreground_process_not_allowlisted":
					guidance = "Bring the approved game to the foreground and try again."
				elif failure_code == "screen_observation_request_timeout":
					guidance = "The foreground game did not return the requested frame in time."
				var failure_detail := failure_code if not failure_code.is_empty() else "unknown"
				_finish_stream_failure(
					"Game-screen observation could not run (" + failure_detail + "). " + guidance)
			elif code == "chat_input_too_large":
				_finish_stream_failure("That message and its current context exceed the gaming reply limit. Shorten the message and try again.")
			else:
				_finish_stream_failure("The streamed reply was not completed (%s)." % code)
		_:
			return


func _finish_stream_success() -> void:
	_pending_action = ""
	_message_input.editable = true
	_send_button.disabled = false
	_chat_request_started_usec = 0
	_stream_user_message = ""
	_stream_recovery_attempt = 0
	_close_stream_client()
	_message_input.grab_focus()


func _finish_stream_failure(message: String) -> void:
	if _stream_reply_message_index >= 0 and _stream_reply_message_index < _messages.size():
		_messages[_stream_reply_message_index] = "SentientOS (not committed): " + _stream_reply_text
		_render_history()
	_close_stream_client()
	_fail_request(message)


func _finish_stream_transport() -> void:
	if _stream_response_code >= 400:
		var parsed: Variant = JSON.parse_string(_stream_error_body.get_string_from_utf8())
		var detail := "HTTP %d" % _stream_response_code
		if parsed is Dictionary and parsed.get("detail") is String:
			detail = str(parsed["detail"])
		_finish_stream_failure("SentientOS: " + detail)
		return
	if not _stream_buffer.strip_edges().is_empty():
		var trailing_event := _stream_buffer
		_stream_buffer = ""
		_consume_stream_event_text(trailing_event)
		if _stream_client == null:
			return
	_close_stream_client()
	_stream_recovery_attempt = 0
	_request_stream_commit_recovery()


func _request_stream_commit_recovery() -> void:
	if _session_id.is_empty() or _stream_user_message.is_empty():
		_finish_stream_failure("The stream closed before SentientOS committed a complete reply.")
		return
	_pending_action = "recover_stream_commit"
	var error := _request.request(
		API_BASE + "/sessions/" + _session_id.uri_encode() + "/turns")
	if error != OK:
		_retry_stream_commit_recovery()


func _handle_stream_commit_recovery(result: int, response_code: int, body: PackedByteArray) -> void:
	if result == HTTPRequest.RESULT_SUCCESS and response_code >= 200 and response_code < 300:
		var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
		if parsed is Dictionary:
			var turns: Variant = parsed.get("turns", [])
			if turns is Array:
				for index in range(turns.size() - 2, -1, -1):
					var user_turn: Variant = turns[index]
					if (not user_turn is Dictionary
							or user_turn.get("role") != "user"
							or str(user_turn.get("text", "")) != _stream_user_message):
						continue
					var assistant_turn: Variant = turns[index + 1]
					if (not assistant_turn is Dictionary
							or assistant_turn.get("role") != "assistant"):
						break
					var committed_answer := str(assistant_turn.get("text", ""))
					if committed_answer.is_empty():
						break
					_last_completed_turn_id = str(assistant_turn.get("turn_id", ""))
					_last_integrity_summary = _summarize_answer_integrity(
						assistant_turn.get("response_diagnostics", {}), committed_answer)
					_stream_reply_text = committed_answer
					if _stream_reply_message_index < 0:
						_stream_reply_message_index = _messages.size()
						_messages.append("")
					_messages[_stream_reply_message_index] = "SentientOS: " + committed_answer
					_render_history()
					_pending_action = ""
					_finish_stream_success()
					return
	_retry_stream_commit_recovery()


func _retry_stream_commit_recovery() -> void:
	if _stream_recovery_attempt < 3:
		_stream_recovery_attempt += 1
		_stream_recovery_timer.start(0.35)
		return
	_pending_action = ""
	_finish_stream_failure("The stream closed before SentientOS committed a complete reply.")


func _close_stream_client() -> void:
	if _stream_client != null:
		_stream_client.close()
		_stream_client = null
	_stream_request_sent = false
	_stream_seen_body = false
	_stream_buffer = ""
	_stream_error_body = PackedByteArray()


func _finish_non_streamed_chat(parsed: Dictionary) -> void:
	_last_completed_turn_id = str(parsed.get("turn_id", ""))
	_last_integrity_summary = _summarize_answer_integrity(
		parsed.get("response_diagnostics", {}), str(parsed.get("response", "")))
	_update_session_status()
	var answer := str(parsed.get("response", ""))
	_append_message("SentientOS", answer if not answer.is_empty() else "I couldn't produce a reply.")
	var context_value: Variant = parsed.get("context", {})
	var context: Dictionary = context_value if context_value is Dictionary else {}
	var timing_value: Variant = context.get("inference_timing", {})
	var round_trip_ms := 0
	if _chat_request_started_usec > 0:
		round_trip_ms = int((Time.get_ticks_usec() - _chat_request_started_usec) / 1000)
	if timing_value is Dictionary:
		var timing_summary := _format_inference_timing(timing_value, round_trip_ms)
		if not timing_summary.is_empty():
			_last_timing_summary = timing_summary
			_update_session_status()
	_chat_request_started_usec = 0


func _format_inference_timing(timing: Dictionary, round_trip_ms: int,
		first_ui_update_ms: int = -1) -> String:
	var parts := PackedStringArray()
	if round_trip_ms > 0:
		parts.append("round trip %.1fs" % (float(round_trip_ms) / 1000.0))
	if first_ui_update_ms >= 0:
		parts.append("first UI update %.1fs" % (float(first_ui_update_ms) / 1000.0))
	var invocation_ms: Variant = timing.get("invocation_latency_ms")
	if invocation_ms is int:
		parts.append("invocation %.1fs" % (float(invocation_ms) / 1000.0))
	if timing.get("backend_metrics_status") == "available":
		var first_content: Variant = timing.get("first_content_chunk_duration_ns")
		if first_content is int:
			parts.append("first content %.1fs" % (float(first_content) / 1000000000.0))
		var load_ns: Variant = timing.get("load_duration_ns")
		if load_ns is int:
			parts.append("load %.1fs" % (float(load_ns) / 1000000000.0))
		var prompt_ns: Variant = timing.get("prompt_evaluation_duration_ns")
		if prompt_ns is int:
			parts.append("prompt %.1fs" % (float(prompt_ns) / 1000000000.0))
		var generation_ns: Variant = timing.get("generation_duration_ns")
		if generation_ns is int:
			parts.append("decode %.1fs" % (float(generation_ns) / 1000000000.0))
	return " · ".join(parts)


func _fail_request(message: String) -> void:
	_pending_action = ""
	_next_after_profile = ""
	_chat_request_started_usec = 0
	_start_button.disabled = false
	_resume_button.disabled = false
	_start_button.text = "New chat"
	_resume_button.text = "Resume latest"
	_update_session_status()
	_message_input.editable = not _session_id.is_empty()
	_send_button.disabled = _session_id.is_empty()
	_screen_observation_toggle.disabled = _session_id.is_empty()
	_append_message("Status", message)


func _update_session_status() -> void:
	var details := PackedStringArray()
	if _session_id.is_empty():
		_session_status_label.text = "Choose Resume latest or New chat."
	else:
		_session_status_label.text = "Conversation ready"
		details.append("Conversation ID: " + _session_id)
	if not _last_completed_turn_id.is_empty():
		details.append("Latest reply turn ID: " + _last_completed_turn_id)
	if not _last_integrity_summary.is_empty():
		details.append(_last_integrity_summary)
	if not _last_timing_summary.is_empty():
		details.append("Timing: " + _last_timing_summary)
	_session_status_label.tooltip_text = " · ".join(details)


func _summarize_answer_integrity(diagnostics: Variant, displayed_text: String) -> String:
	if not diagnostics is Dictionary:
		return "Answer integrity unavailable."
	var hasher := HashingContext.new()
	if hasher.start(HashingContext.HASH_SHA256) != OK:
		return "Answer integrity unavailable."
	hasher.update(displayed_text.to_utf8_buffer())
	var displayed_digest := hasher.finish().hex_encode()
	var transcript_matches: bool = diagnostics.get("transcript_text_sha256") == displayed_digest
	var delivery_matches: bool = diagnostics.get("delivery_text_sha256") == displayed_digest
	if not transcript_matches or not delivery_matches:
		return "Displayed answer digest mismatch or lineage unavailable."
	var raw_digest: Variant = diagnostics.get("invocation_output_text_sha256")
	var lineage_status := str(diagnostics.get("status", "unknown"))
	if not raw_digest is String:
		return "Displayed answer matches transcript/API; raw inference digest unavailable."
	if raw_digest == displayed_digest and lineage_status == "exact_invocation_output_match":
		return "Displayed answer matches raw, transcript, and API digests."
	if raw_digest == displayed_digest:
		return "Displayed answer matches transcript/API and raw digest; lineage: %s." % lineage_status
	return "Displayed answer matches transcript/API; raw inference differs (%s)." % lineage_status


func _append_message(speaker: String, text: String) -> void:
	_messages.append("%s: %s" % [speaker, text])
	while _messages.size() > MAX_VISIBLE_MESSAGES:
		_messages.remove_at(0)
	_render_history()


func _render_history() -> void:
	if _history == null:
		return
	for child in _history.get_children():
		child.queue_free()
	var first_visible := maxi(0, _messages.size() - MAX_VISIBLE_MESSAGES)
	for index in range(first_visible, _messages.size()):
		var entry := _messages[index]
		var separator := entry.find(":")
		var speaker := entry.substr(0, separator) if separator >= 0 else "SentientOS"
		var body := entry.substr(separator + 1).strip_edges() if separator >= 0 else entry
		var is_assistant := speaker.begins_with("SentientOS")
		var card := PanelContainer.new()
		var style := StyleBoxFlat.new()
		style.bg_color = Color(0.025, 0.075, 0.095, 0.98) if is_assistant else Color(0.055, 0.12, 0.17, 0.98)
		style.content_margin_left = 10
		style.content_margin_right = 10
		style.content_margin_top = 7
		style.content_margin_bottom = 7
		style.corner_radius_top_left = 6
		style.corner_radius_top_right = 6
		style.corner_radius_bottom_left = 6
		style.corner_radius_bottom_right = 6
		if is_assistant and index == _messages.size() - 1:
			style.border_width_left = 3
			style.border_color = Color(0.2, 0.72, 0.84, 0.95)
		card.add_theme_stylebox_override("panel", style)
		card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		_history.add_child(card)
		var content := VBoxContainer.new()
		content.add_theme_constant_override("separation", 3)
		card.add_child(content)
		var speaker_label := Label.new()
		speaker_label.text = speaker
		speaker_label.add_theme_font_size_override("font_size", 13)
		speaker_label.add_theme_color_override("font_color", Color(0.55, 0.85, 0.91) if is_assistant else Color(0.68, 0.82, 0.96))
		content.add_child(speaker_label)
		var reply_label := Label.new()
		reply_label.text = body
		reply_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		reply_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		reply_label.add_theme_color_override("font_color", Color(0.94, 0.97, 0.98))
		reply_label.add_theme_font_size_override("font_size", 20 if is_assistant and index == _messages.size() - 1 else 18)
		content.add_child(reply_label)
	call_deferred("_scroll_history_to_latest")


func _scroll_history_to_latest() -> void:
	await get_tree().process_frame
	if _history_scroll == null:
		return
	var scrollbar := _history_scroll.get_v_scroll_bar()
	if scrollbar != null:
		scrollbar.value = scrollbar.max_value


func _on_settings_toggled(expanded: bool) -> void:
	if _settings_panel != null:
		_settings_panel.visible = expanded
	if _settings_button != null:
		_settings_button.text = "Hide settings" if expanded else "Settings"


func _on_overlay_drag_handle_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT \
		and event.pressed and DisplayServer.has_feature(DisplayServer.FEATURE_WINDOW_DRAG):
		DisplayServer.window_start_drag()
