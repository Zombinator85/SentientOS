from __future__ import annotations

import pytest

from sentientos.actuators.gui_control import GUIConfig, GUIControlError, GUIController


def test_gui_control_policy_and_panic() -> None:
    actions: list[tuple[str, dict]] = []

    def mouse(action: str, payload: dict) -> None:
        actions.append((action, payload))

    def keyboard(action: str, payload: dict) -> None:
        actions.append((action, payload))

    controller = GUIController(
        GUIConfig(enable=True, safety="standard"),
        mouse_driver=mouse,
        keyboard_driver=keyboard,
        panic_flag=lambda: False,
    )

    controller.move(x=10, y=20)
    controller.click(x=5, y=5)
    with pytest.raises(GUIControlError):
        controller.type_text("password=secret")

    permissive = GUIController(
        GUIConfig(enable=True, safety="permissive"),
        mouse_driver=mouse,
        keyboard_driver=keyboard,
        panic_flag=lambda: True,
    )

    with pytest.raises(GUIControlError):
        permissive.click(x=1, y=1)

    permissive = GUIController(
        GUIConfig(enable=True, safety="permissive"),
        mouse_driver=mouse,
        keyboard_driver=keyboard,
        panic_flag=lambda: False,
    )
    permissive.type_text("safe text")
    assert actions[0][0] == "move"
    assert permissive.status()["mode"] == "permissive"
