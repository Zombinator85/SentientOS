import pytest

from sentientos.codex.codex_quiet_mode import CodexQuietMode


pytestmark = pytest.mark.no_legacy_skip


def test_codex_quiet_mode_suggests_when_stable():
    quiet_mode = CodexQuietMode(delta_threshold=0.1)

    decision = quiet_mode.assess(context_stable=True, degradation_signals=[], observer_delta=0.05)

    assert decision["quiet"] is True
    assert decision["plan"].effects["expansion_proposals"] == "suppressed"
    assert "Context stable" in decision["plan"].reasons[0]


def test_codex_quiet_mode_respects_degradation():
    quiet_mode = CodexQuietMode(delta_threshold=0.1)

    decision = quiet_mode.assess(context_stable=True, degradation_signals=[{"status": "warn"}], observer_delta=0.05)

    assert decision["quiet"] is False
    assert decision["plan"].effects["restructuring"] == "enabled"
