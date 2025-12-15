extends Node

@export var animation_player_path: NodePath
@export var default_motion := "idle"
@export var supported_motions := ["idle", "wave", "nod"]

var _active_motion := ""


func _ready() -> void:
    _play(default_motion)


func apply_motion(motion: String) -> void:
    var player := _resolve_player()
    if player == null:
        return

    var target := motion if motion in supported_motions else default_motion
    if target == _active_motion:
        return

    _play(target)


func _resolve_player():
    if animation_player_path == NodePath(""):
        return null
    return get_node_or_null(animation_player_path)


func _play(name: String) -> void:
    var player := _resolve_player()
    if player == null:
        return
    if player.has_animation(name):
        player.play(name)
        _active_motion = name
