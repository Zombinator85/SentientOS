extends Node

@export var listen_port := 18188
@export var listen_port := 18188
@export var blendshape_driver_path: NodePath
@export var motion_driver_path: NodePath
@export var status_label_path: NodePath

var _server := UDPServer.new()
var _last_packet := {}


func _ready() -> void:
    _server.listen(listen_port)
    _write_status("Listening on UDP %d" % listen_port)


func _process(_delta: float) -> void:
    if not _server.is_listening():
        return

    _server.poll()
    while _server.is_connection_available():
        var peer := _server.take_connection()
        _drain_peer(peer)


func _drain_peer(peer: PacketPeerUDP) -> void:
    while peer.get_available_packet_count() > 0:
        var packet := peer.get_packet().get_string_from_utf8()
        var payload := JSON.parse_string(packet)
        if typeof(payload) == TYPE_DICTIONARY:
            _apply_state(payload)


func _apply_state(state: Dictionary) -> void:
    _last_packet = state
    var expression := state.get("expression", "rest")
    var mood := state.get("mood", "calm")
    var intensity := float(state.get("intensity", 0.0))
    var motion := state.get("motion", "idle")
    var phrase := state.get("current_phrase", "")
    var speaking := bool(state.get("is_speaking", false))
    var status := "%s @ %.2f (%s)" % [expression, intensity, motion]
    if speaking and phrase != "":
        status += " – %s" % phrase
    _write_status(status)

    var blendshape_driver := _resolve_node(blendshape_driver_path)
    if blendshape_driver and blendshape_driver.has_method("apply_expression"):
        blendshape_driver.apply_expression(expression, mood, intensity)
        var visemes := state.get("viseme_timeline", [])
        if visemes is Array and blendshape_driver.has_method("play_viseme_timeline"):
            blendshape_driver.play_viseme_timeline(visemes, state.get("timestamp", 0.0))

    var motion_driver := _resolve_node(motion_driver_path)
    if motion_driver and motion_driver.has_method("apply_motion"):
        motion_driver.apply_motion(motion)


func _write_status(message: String) -> void:
    var label := _resolve_node(status_label_path)
    if label and label.has_method("set_text"):
        label.text = message


func _resolve_node(path: NodePath):
    if path == NodePath(""):
        return null
    return get_node_or_null(path)
