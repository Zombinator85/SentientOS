"""Canonical privileged surface for SentientOS.

This document lives in code so privilege boundaries stay explicit and enforced
by tests. Update deliberately if new execution/control modules are introduced.
"""
from __future__ import annotations

PRIVILEGED_MODULE_PREFIXES = (
    "task_executor",
    "task_admission",
    "control_plane",
)

# Relative file paths that are allowed to import privileged modules above.
PRIVILEGED_IMPORT_ALLOWLIST = {
    "autonomous_self_patching_agent.py",
    "self_patcher.py",
    "sentientos/dashboard/dashboard_snapshot.py",
    "speech_emitter.py",
    "speech_to_avatar_bridge.py",
    "task_admission.py",
    "task_executor.py",
    "tts_test.py",
}
