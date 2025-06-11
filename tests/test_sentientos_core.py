"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import sentientos.core as sc
from sentientos import __version__


def test_core_greet():
    c = sc.Core("tester")
    assert c.greet() == "Hello from tester"


def test_version_str():
    assert isinstance(__version__, str)
