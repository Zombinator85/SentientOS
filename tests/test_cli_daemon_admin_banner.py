"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.
import importlib
import argparse
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pytest

import admin_utils

CLI_MODULES = [
    "affirmation_webhook_cli",
    "avatar_invocation_cli",
    "blessing_recap_cli",
    "cathedral_liturgy_cli",
    "diff_memory_cli",
    "doctrine_cli",
    "emotion_arc_cli",
    "experiment_cli",
    "federation_recap_cli",
    "heartbeat_monitor_cli",
    "heatmap_cli",
    "heirloom_sync_cli",
    "heresy_cli",
    "memory_tomb_cli",
    "neos_avatar_crowning_cli",
    "neos_festival_law_vote_cli",
    "neos_spiral_playback_cli",
    "plugins_cli",
    "reflect_cli",
    "reflection_tag_cli",
    "review_heresy_cli",
    "ritual_cli",
    "ritual_digest_cli",
    "public_review_recap",
    "theme_cli",
    "treasury_cli",
    "trust_cli",
    "genesis_oracle",
    "neos_federation_presence_ledger_exporter",
    "spiral_law_chronicle_compiler",
]

DAEMON_MODULES = {
    "avatar_council_succession_daemon": "main",
    "avatar_dream_daemon": "main",
    "ledger_seal_daemon": "cli",
    "neos_living_law_recursion_daemon": "main",
    "neos_ritual_law_audit_daemon": "main",
    "neos_teaching_festival_daemon": "main",
    "resonite_consent_daemon": "main",
    "resonite_presence_festival_spiral_diff_daemon": "main",
    "spiral_dream_goal_daemon": "main",
}

@pytest.mark.parametrize("mod_name", CLI_MODULES)
def test_cli_requires_admin(monkeypatch, mod_name):
    calls = []
    monkeypatch.setattr(admin_utils, "require_admin_banner", lambda: calls.append(True))
    mod = importlib.import_module(mod_name)
    if mod_name == "heartbeat_monitor_cli":
        monkeypatch.setattr(mod, "monitor", lambda *a, **k: (_ for _ in ()).throw(SystemExit))
        with pytest.raises(SystemExit):
            mod.main()
    elif mod_name == "federation_recap_cli":
        with pytest.raises(Exception):
            mod.main()
    else:
        monkeypatch.setattr(argparse.ArgumentParser, "parse_args", lambda *a, **k: (_ for _ in ()).throw(SystemExit))
        with pytest.raises(SystemExit):
            mod.main()
    assert calls

@pytest.mark.parametrize("mod_name, func_name", DAEMON_MODULES.items())
def test_daemon_requires_admin(monkeypatch, mod_name, func_name):
    calls = []
    monkeypatch.setattr(admin_utils, "require_admin_banner", lambda: calls.append(True))
    mod = importlib.import_module(mod_name)
    if mod_name == "resonite_presence_festival_spiral_diff_daemon":
        monkeypatch.setattr(argparse.ArgumentParser, "parse_args", lambda *a, **k: argparse.Namespace(world_a='a', world_b='b', user='u'))
        monkeypatch.setattr(mod, "log_diff", lambda *a, **k: (_ for _ in ()).throw(SystemExit))
        with pytest.raises(SystemExit):
            getattr(mod, func_name)()
    else:
        monkeypatch.setattr(argparse.ArgumentParser, "parse_args", lambda *a, **k: (_ for _ in ()).throw(SystemExit))
        with pytest.raises(SystemExit):
            getattr(mod, func_name)()
    assert calls
