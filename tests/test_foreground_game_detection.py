from __future__ import annotations

import hashlib
from threading import Lock

import pytest

from sentientos.foreground_game_detection import (
    ForegroundGameDetector,
    normalize_game_process_names,
)
from sentientos.local_model_serving_inference import ProductionServingInferenceController

pytestmark = pytest.mark.no_legacy_skip
STAMP = "2026-11-02T00:00:00+00:00"


def test_foreground_allowlist_match_returns_digest_without_process_name() -> None:
    detector = ForegroundGameDetector(
        process_name_provider=lambda: "ExampleGame.exe",
        system_provider=lambda: "Windows",
        clock=lambda: STAMP,
    )

    observation = detector.observe(("examplegame.EXE",))

    assert observation.status == "available"
    assert observation.game_foreground is True
    assert observation.process_name_digest == hashlib.sha256(
        b"examplegame.exe").hexdigest()
    assert "ExampleGame" not in str(observation.to_dict())
    assert observation.observed_at == STAMP


def test_nonmatching_foreground_process_is_not_a_game() -> None:
    detector = ForegroundGameDetector(
        process_name_provider=lambda: "explorer.exe",
        system_provider=lambda: "Windows",
        clock=lambda: STAMP,
    )

    observation = detector.observe(("examplegame.exe",))

    assert observation.status == "available"
    assert observation.game_foreground is False


def test_unsupported_or_unavailable_observation_is_unknown() -> None:
    unsupported = ForegroundGameDetector(
        system_provider=lambda: "Linux", clock=lambda: STAMP)
    failed = ForegroundGameDetector(
        process_name_provider=lambda: (_ for _ in ()).throw(OSError()),
        system_provider=lambda: "Windows", clock=lambda: STAMP)

    assert unsupported.observe(("examplegame.exe",)).status == "unsupported_platform"
    assert failed.observe(("examplegame.exe",)).status == "observation_failed"


@pytest.mark.parametrize("names", [(), ("../game.exe",), ("C:\\game.exe",), ("game",),
                                     ("game.exe", "GAME.EXE")])
def test_game_allowlist_rejects_empty_paths_invalid_names_and_duplicates(names) -> None:
    with pytest.raises(ValueError):
        normalize_game_process_names(names)


def test_automatic_mode_fails_safe_when_background_process_observation_is_unknown() -> None:
    detector = ForegroundGameDetector(
        process_name_provider=lambda: "godot.exe",
        running_process_names_provider=lambda: None,
        system_provider=lambda: "Windows", clock=lambda: STAMP)
    controller = _workload_controller(detector)
    controller.set_workload_mode("automatic", ("ExampleGame.exe",))

    state = controller.current_workload_state()

    assert state["game_foreground"] is False
    assert state["game_process_running"] is None
    assert state["effective_mode"] == "gaming"
    assert state["mode_source"] == "game_process_observation_unavailable_conservative_gaming"


def _workload_controller(detector: ForegroundGameDetector) -> ProductionServingInferenceController:
    controller = object.__new__(ProductionServingInferenceController)
    controller._workload_lock = Lock()
    controller._workload_mode = "normal"
    controller._game_process_names = ()
    controller._foreground_game_detector = detector
    return controller


def test_automatic_mode_tightens_only_for_allowlisted_foreground_game() -> None:
    detector = ForegroundGameDetector(
        process_name_provider=lambda: "ExampleGame.exe",
        running_process_names_provider=lambda: (),
        system_provider=lambda: "Windows", clock=lambda: STAMP)
    controller = _workload_controller(detector)

    controller.set_workload_mode("automatic", ("ExampleGame.exe",))

    state = controller.current_workload_state()
    assert state["mode"] == "automatic"
    assert state["effective_mode"] == "gaming"
    assert state["mode_source"] == "foreground_allowlist_match"
    assert state["process_name_digest"] == hashlib.sha256(b"examplegame.exe").hexdigest()


def test_automatic_mode_uses_normal_profile_for_other_foreground_apps() -> None:
    detector = ForegroundGameDetector(
        process_name_provider=lambda: "explorer.exe",
        running_process_names_provider=lambda: (),
        system_provider=lambda: "Windows", clock=lambda: STAMP)
    controller = _workload_controller(detector)
    controller.set_workload_mode("automatic", ("ExampleGame.exe",))

    state = controller.current_workload_state()

    assert state["effective_mode"] == "normal"
    assert state["mode_source"] == "foreground_allowlist_no_match"
    assert state["configured_game_process_names"] == ["examplegame.exe"]


def test_automatic_mode_falls_back_to_low_work_profile_when_detection_fails() -> None:
    detector = ForegroundGameDetector(system_provider=lambda: "Linux", clock=lambda: STAMP)
    controller = _workload_controller(detector)
    controller.set_workload_mode("automatic", ("ExampleGame.exe",))

    state = controller.current_workload_state()

    assert state["effective_mode"] == "gaming"
    assert state["mode_source"] == "foreground_observation_unavailable_conservative_gaming"
    assert state["game_foreground"] is None


def test_background_allowlisted_game_process_is_reported_without_claiming_foreground() -> None:
    detector = ForegroundGameDetector(
        process_name_provider=lambda: "godot.exe",
        running_process_names_provider=lambda: ("Cronos-Win64-Shipping.exe", "godot.exe"),
        system_provider=lambda: "Windows",
        clock=lambda: STAMP,
    )

    observation = detector.observe(("cronos-win64-shipping.exe",))

    assert observation.status == "available"
    assert observation.game_foreground is False
    assert observation.game_process_running is True
    assert observation.running_process_name_digests == (
        hashlib.sha256(b"cronos-win64-shipping.exe").hexdigest(),)
    serialized = str(observation.to_dict())
    assert "Cronos" not in serialized
    assert "godot.exe" not in serialized


def test_unavailable_process_list_does_not_claim_no_game_running() -> None:
    detector = ForegroundGameDetector(
        process_name_provider=lambda: "godot.exe",
        running_process_names_provider=lambda: None,
        system_provider=lambda: "Windows",
        clock=lambda: STAMP,
    )

    observation = detector.observe(("cronos.exe",))

    assert observation.game_foreground is False
    assert observation.game_process_running is None
    assert observation.running_process_name_digests is None
