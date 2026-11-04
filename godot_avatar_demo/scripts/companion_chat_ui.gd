extends Control
## Development-only text interface for the supervised loopback chat service.
## It never enables screen observation or requests transcript retention.

const API_BASE := "http://127.0.0.1:5000"
const MAX_VISIBLE_MESSAGES := 40

var _request: HTTPRequest
var _history: RichTextLabel
var _start_button: Button
var _resume_button: Button
var _message_input: LineEdit
var _send_button: Button
var _session_id := ""
var _pending_action := ""
var _next_after_profile := ""
var _messages := PackedStringArray()


func _ready() -> void:
	_build_interface()
	_request = HTTPRequest.new()
	_request.timeout = 120.0
	_request.use_threads = true
	add_child(_request)
	_request.request_completed.connect(_on_request_completed)
	_append_message("SentientOS", "Local development chat. Screen observation is off; turns are not retained as memories. Choose New chat or Resume latest.")


func _build_interface() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var panel := PanelContainer.new()
	panel.name = "ChatPanel"
	panel.anchor_left = 0.025
	panel.anchor_top = 1.0
	panel.anchor_right = 0.975
	panel.anchor_bottom = 1.0
	panel.offset_top = -174.0
	panel.offset_bottom = -12.0
	var panel_style := StyleBoxFlat.new()
	panel_style.bg_color = Color(0.025, 0.045, 0.06, 0.94)
	panel_style.corner_radius_top_left = 8
	panel_style.corner_radius_top_right = 8
	panel_style.corner_radius_bottom_left = 8
	panel_style.corner_radius_bottom_right = 8
	panel.add_theme_stylebox_override("panel", panel_style)
	add_child(panel)

	var layout := VBoxContainer.new()
	layout.add_theme_constant_override("separation", 6)
	panel.add_child(layout)
	_history = RichTextLabel.new()
	_history.name = "Conversation"
	_history.bbcode_enabled = false
	_history.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_history.fit_content = false
	_history.scroll_active = true
	_history.scroll_following = true
	_history.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_history.add_theme_color_override("default_color", Color(0.86, 0.92, 0.94))
	_history.add_theme_font_size_override("normal_font_size", 14)
	layout.add_child(_history)

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	layout.add_child(row)
	_start_button = Button.new()
	_start_button.text = "New chat"
	_start_button.pressed.connect(_start_chat)
	row.add_child(_start_button)
	_resume_button = Button.new()
	_resume_button.text = "Resume latest"
	_resume_button.pressed.connect(_resume_chat)
	row.add_child(_resume_button)
	_message_input = LineEdit.new()
	_message_input.placeholder_text = "Message SentientOS…"
	_message_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_message_input.editable = false
	_message_input.text_submitted.connect(_send_message)
	row.add_child(_message_input)
	_send_button = Button.new()
	_send_button.text = "Send"
	_send_button.disabled = true
	_send_button.pressed.connect(_send_message.bind(""))
	row.add_child(_send_button)


func _start_chat() -> void:
	_select_profile_then("create_session")


func _resume_chat() -> void:
	_select_profile_then("load_sessions")


func _select_profile_then(next_action: String) -> void:
	if not _pending_action.is_empty():
		return
	_next_after_profile = next_action
	_pending_action = "set_gaming_mode"
	_start_button.disabled = true
	_resume_button.disabled = true
	_start_button.text = "Selecting game-safe profile…"
	var headers := PackedStringArray(["Content-Type: application/json"])
	var body_text := JSON.stringify({"mode": "gaming"})
	var error := _request.request(API_BASE + "/workload-mode", headers, HTTPClient.METHOD_POST, body_text)
	if error != OK:
		_fail_request("Could not select the game-safe profile (%s)." % error_string(error))


func _send_message(submitted_text: String = "") -> void:
	if _session_id.is_empty() or not _pending_action.is_empty():
		return
	var message := submitted_text if not submitted_text.is_empty() else _message_input.text
	message = message.strip_edges()
	if message.is_empty():
		return
	_append_message("You", message)
	_message_input.clear()
	_message_input.editable = false
	_send_button.disabled = true
	_pending_action = "chat"
	var request_body := JSON.stringify({
		"message": message,
		"session_id": _session_id,
		"retain": false,
		"request_id": "godot-ui-%d-%d" % [Time.get_ticks_usec(), randi()],
		"observe_screen": false,
	})
	var headers := PackedStringArray(["Content-Type: application/json"])
	var error := _request.request(API_BASE + "/chat", headers, HTTPClient.METHOD_POST, request_body)
	if error != OK:
		_fail_request("The chat request could not start (%s)." % error_string(error))


func _on_request_completed(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
	var array_response_allowed := _pending_action == "load_sessions" and parsed is Array
	if result != HTTPRequest.RESULT_SUCCESS or response_code < 200 or response_code >= 300 or (not parsed is Dictionary and not array_response_allowed):
		var detail := "SentientOS request failed (HTTP %d, result %d)." % [response_code, result]
		if parsed is Dictionary and parsed.get("detail") is String:
			detail = "SentientOS: " + str(parsed["detail"])
		_fail_request(detail)
		return
	match _pending_action:
		"set_gaming_mode":
			if parsed.get("effective_mode") != "gaming":
				_fail_request("SentientOS did not confirm the game-safe profile.")
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
			_pending_action = "enable_avatar"
			var output_body := JSON.stringify({"session_id": _session_id, "enabled": true})
			var headers := PackedStringArray(["Content-Type: application/json"])
			var error := _request.request(API_BASE + "/avatar-output", headers, HTTPClient.METHOD_POST, output_body)
			if error != OK:
				_fail_request("The visual companion connection could not resume (%s)." % error_string(error))
		"create_session":
			_session_id = str(parsed.get("session_id", ""))
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
			_start_button.text = "New chat"
			_resume_button.text = "Resumed"
			_start_button.disabled = false
			_resume_button.disabled = true
			_message_input.editable = true
			_send_button.disabled = false
			_message_input.grab_focus()
			_append_message("SentientOS", "Connected. Your replies will also appear beside the companion.")
		"chat":
			_pending_action = ""
			_message_input.editable = true
			_send_button.disabled = false
			var answer := str(parsed.get("response", ""))
			_append_message("SentientOS", answer if not answer.is_empty() else "I couldn't produce a reply.")
			_message_input.grab_focus()
		_:
			_fail_request("The local chat service returned an unexpected response.")


func _fail_request(message: String) -> void:
	_pending_action = ""
	_next_after_profile = ""
	_start_button.disabled = false
	_resume_button.disabled = false
	_start_button.text = "New chat"
	_resume_button.text = "Resume latest"
	_message_input.editable = not _session_id.is_empty()
	_send_button.disabled = _session_id.is_empty()
	_append_message("Status", message)


func _append_message(speaker: String, text: String) -> void:
	_messages.append("%s: %s" % [speaker, text])
	while _messages.size() > MAX_VISIBLE_MESSAGES:
		_messages.remove_at(0)
	if _history != null:
		_history.text = char(10).join(_messages)
