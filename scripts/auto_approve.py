from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()
require_lumos_approval()

import os
import sys


def prompt_yes_no(prompt: str, default: bool = True) -> bool:
    """Return user consent or auto-approve based on environment.

    If ``LUMOS_AUTO_APPROVE`` or ``SENTIENTOS_HEADLESS`` is set, or the
    session is non-interactive, the ``default`` response is returned.
    Otherwise the user is prompted with ``input``.
    """
    if (
        os.getenv("LUMOS_AUTO_APPROVE") == "1"
        or os.getenv("SENTIENTOS_HEADLESS") == "1"
        or not sys.stdin.isatty()
    ):
        return default
    try:
        ans = input(f"{prompt} [y/N]: ")
    except EOFError:
        ans = ""
    return ans.strip().lower() in {"y", "yes"}
