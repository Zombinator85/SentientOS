"""Public dashboard boundary façade.

Provides dashboard-safe helpers for ledger-derived widgets and mood blessings
without exposing raw ledger internals to dashboard/expressive modules.
"""
from __future__ import annotations

from typing import Any

import ledger


def render_ledger_widget(target: Any) -> None:
    """Render the canonical ledger streamlit widget on ``target``."""
    ledger.streamlit_widget(target)


def log_mood_blessing(user: str, mood: str, phrase: str) -> dict[str, str]:
    """Delegate mood blessing to canonical ledger semantics."""
    return ledger.log_mood_blessing(user, "public", {mood: 1.0}, phrase)


__all__ = ["render_ledger_widget", "log_mood_blessing"]
