"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import warnings
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from privilege_lint._compat import safe_import


def test_safe_import_stub():
    with warnings.catch_warnings(record=True) as w:
        mod = safe_import('no_mod_xyz', stub={'sentinel': None})
    assert hasattr(mod, 'sentinel')
    assert w and 'no_mod_xyz' in str(w[0].message)


def test_safe_import_suppressed_warning():
    with warnings.catch_warnings(record=True) as w:
        mod = safe_import('no_mod_xyz', stub={'sentinel': None}, warn=False)
    assert hasattr(mod, 'sentinel')
    assert not w
