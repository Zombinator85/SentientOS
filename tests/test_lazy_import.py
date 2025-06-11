import warnings
import os, sys
from sentientos.privilege_lint._compat import safe_import


def test_safe_import_stub():
    with warnings.catch_warnings(record=True) as w:
        mod = safe_import('no_mod_xyz', stub={'sentinel': None})
    assert hasattr(mod, 'sentinel')
    assert w and 'no_mod_xyz' in str(w[0].message)
