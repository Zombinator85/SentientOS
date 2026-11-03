from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from tests.godot_runtime import godot_executable
from avatar_state import AvatarState, AvatarStateEmitter
from godot_avatar_receiver import AvatarStateForwarder

pytestmark = pytest.mark.no_legacy_skip


def test_godot_avatar_demo_scripts_parse_in_supported_engine(tmp_path: Path) -> None:
    executable = godot_executable()
    if executable is None:
        pytest.skip("Godot is unavailable in this validation environment")

    source = Path(__file__).parents[1] / "godot_avatar_demo"
    project = tmp_path / "godot_avatar_demo"
    shutil.copytree(source, project, ignore=shutil.ignore_patterns(".godot", "*.uid"))
    home = tmp_path / "godot-home"
    cache = tmp_path / "godot-cache"
    font_cache = tmp_path / "font-cache"
    for directory in (home, cache, font_cache):
        directory.mkdir()

    result = subprocess.run(
        [executable, "--headless", "--path", str(project), "--editor", "--quit"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
        env={
            "PATH": os.defpath,
            "HOME": str(home),
            "XDG_CACHE_HOME": str(cache),
            "FONTCONFIG_CACHE_DIR": str(font_cache),
        },
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "Failed to load script" not in output, output


def test_godot_companion_scene_instantiates_and_responds_to_avatar_state(tmp_path: Path) -> None:
    executable = godot_executable()
    if executable is None:
        pytest.skip("Godot is unavailable in this validation environment")

    source = Path(__file__).parents[1] / "godot_avatar_demo"
    project = tmp_path / "godot_avatar_demo"
    shutil.copytree(source, project, ignore=shutil.ignore_patterns(".godot", "*.uid"))
    state_path = tmp_path / "avatar_state.json"
    AvatarStateEmitter(state_path).emit(AvatarState(
        mood="joy", intensity=0.8, expression="smile", motion="wave",
        current_phrase="gg", is_speaking=False,
    ))
    packet = AvatarStateForwarder(state_path)._read_state()
    assert packet is not None
    assert packet["phrase"]["text"] == "gg"
    (project / "avatar_packet.json").write_text(json.dumps(packet), encoding="utf-8")
    script = project / "exercise_companion.gd"
    script.write_text(
        "extends SceneTree\n"
        "func _initialize() -> void:\n"
        "\tcall_deferred(\"exercise\")\n"
        "func check(condition: bool, reason: String) -> bool:\n"
        "\tif condition:\n"
        "\t\treturn true\n"
        "\tpush_error(reason)\n"
        "\tquit(1)\n"
        "\treturn false\n"
        "func exercise() -> void:\n"
        "\tvar packed := load(\"res://scenes/avatar_demo.tscn\") as PackedScene\n"
        "\tif not check(packed != null, \"companion_scene_missing\"):\n\t\treturn\n"
        "\tvar scene := packed.instantiate()\n"
        "\tscene.auto_listen = false\n"
        "\troot.add_child(scene)\n"
        "\tawait process_frame\n"
        "\tif not check(scene.get_node(\"Camera3D\").current, \"companion_camera_not_active\"):\n\t\treturn\n"
        "\tif not check(scene.get_node(\"Avatar/HeadPivot/Head\").mesh != null, \"head_mesh_missing\"):\n\t\treturn\n"
        "\tif not check(scene.get_node(\"Avatar/BodyMesh\").mesh != null, \"body_mesh_missing\"):\n\t\treturn\n"
        "\tvar avatar_meshes := scene.get_node(\"Avatar\").find_children(\"*\", \"MeshInstance3D\", true, false)\n"
        "\tif not check(avatar_meshes.size() >= 9, \"companion_geometry_incomplete\"):\n\t\treturn\n"
        "\tvar mouth := scene.get_node(\"Avatar/HeadPivot/Mouth\") as MeshInstance3D\n"
        "\tvar eyes := scene.get_node(\"Avatar/HeadPivot/EyeLeft\") as MeshInstance3D\n"
        "\tvar rest_mouth := mouth.scale.y\n"
        "\tvar face_driver := scene.get_node(\"BlendshapeDriver\")\n"
        "\tface_driver.apply_expression(\"smile\", \"calm\", 1.0)\n"
        "\tif not check(mouth.scale.y > rest_mouth, \"smile_did_not_change_face\"):\n\t\treturn\n"
        "\tif not check(eyes.scale.y < 1.0, \"smile_did_not_change_eyes\"):\n\t\treturn\n"
        "\tvar motion := scene.get_node(\"MotionDriver\")\n"
        "\tvar arm := scene.get_node(\"Avatar/LeftArm\") as Node3D\n"
        "\tvar rest_arm := arm.rotation.z\n"
        "\tmotion.apply_motion(\"wave\")\n"
        "\tawait create_timer(0.2).timeout\n"
        "\tif not check(not is_equal_approx(arm.rotation.z, rest_arm), \"wave_did_not_move_arm\"):\n\t\treturn\n"
        "\tvar head := scene.get_node(\"Avatar/HeadPivot\") as Node3D\n"
        "\tvar rest_head := head.rotation.x\n"
        "\tmotion.apply_motion(\"nod\")\n"
        "\tif not check(is_equal_approx(arm.rotation.z, rest_arm), \"gesture_switch_did_not_reset_arm\"):\n\t\treturn\n"
        "\tawait create_timer(0.16).timeout\n"
        "\tif not check(not is_equal_approx(head.rotation.x, rest_head), \"nod_did_not_move_head\"):\n\t\treturn\n"
        "\tface_driver.apply_expression(\"rest\", \"calm\", 1.0)\n"
        "\tface_driver.play_viseme_timeline([{\"time\": 0.0, \"duration\": 0.16, \"viseme\": \"a\"}])\n"
        "\tawait create_timer(0.07).timeout\n"
        "\tif not check(mouth.scale.y > rest_mouth, \"viseme_did_not_open_mouth\"):\n\t\treturn\n"
        "\tawait create_timer(0.2).timeout\n"
        "\tif not check(is_equal_approx(mouth.scale.y, rest_mouth), \"viseme_did_not_close_mouth\"):\n\t\treturn\n"
        "\tvar packet_text := FileAccess.get_file_as_string(\"res://avatar_packet.json\")\n"
        "\tvar packet: Variant = JSON.parse_string(packet_text)\n"
        "\tif not check(packet is Dictionary, \"avatar_packet_invalid\"):\n\t\treturn\n"
        "\tscene._apply_state(packet as Dictionary)\n"
        "\tif not check(scene.get_node(\"UI/StatusLabel\").text.contains(\"gg\"), \"state_phrase_not_rendered\"):\n\t\treturn\n"
        "\tprint(\"SENTIENTOS_COMPANION_SCENE_READY\")\n"
        "\tquit(0)\n",
        encoding="utf-8",
    )
    home = tmp_path / "godot-home"
    cache = tmp_path / "godot-cache"
    font_cache = tmp_path / "font-cache"
    for directory in (home, cache, font_cache):
        directory.mkdir()
    result = subprocess.run(
        [executable, "--headless", "--path", str(project), "--script", str(script)],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
        env={
            "PATH": os.defpath,
            "HOME": str(home),
            "XDG_CACHE_HOME": str(cache),
            "FONTCONFIG_CACHE_DIR": str(font_cache),
        },
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SENTIENTOS_COMPANION_SCENE_READY" in output, output
    assert "SCRIPT ERROR" not in output, output
