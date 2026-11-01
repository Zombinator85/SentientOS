from __future__ import annotations

import logging

import pytest

from sentientos.persona import PersonaLoop, initial_state

pytestmark = pytest.mark.no_legacy_skip


def _loop() -> PersonaLoop:
    return PersonaLoop(initial_state(), logger=logging.getLogger("test.persona.payloads"))


def test_system_load_summary_ignores_non_mapping_data() -> None:
    summary = _loop()._build_summary(
        [{"kind": "world", "world_kind": "system_load", "data": object()}]
    )

    assert summary == "I noticed a calm system load and I’m feeling calm and curious."


def test_success_summary_ignores_non_string_description() -> None:
    summary = _loop()._build_summary(
        [{"kind": "experiment_result", "success": True, "description": object()}]
    )

    assert summary == "An experiment succeeded; momentum feels good."
