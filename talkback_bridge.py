"""Inert compatibility boundary for the retired camera-talkback bridge."""
from __future__ import annotations


class TalkbackExecutionRetiredError(RuntimeError):
    """Raised when legacy camera-talkback execution is requested."""


class CameraTalkback:
    """Compatibility name that grants no camera-talkback authority."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TalkbackExecutionRetiredError("camera talkback execution is retired")


__all__ = ["CameraTalkback", "TalkbackExecutionRetiredError"]
