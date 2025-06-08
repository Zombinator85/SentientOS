"""Helpers for non-interactive approvals."""
import os


def is_auto_approve() -> bool:
    """Return True if prompts should auto-approve."""
    return os.getenv("LUMOS_AUTO_APPROVE", "") == "1"


def prompt_yes_no(prompt: str) -> bool:
    """Prompt the user, auto-approving when environment variable is set."""
    if is_auto_approve():
        return True
    try:
        return input(f"{prompt} [y/N]: ").lower().startswith("y")
    except EOFError:
        return False
