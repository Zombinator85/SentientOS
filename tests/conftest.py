"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
import builtins
# The admin banner checks can exit the process during module import if not
# stubbed ahead of time. Stub them here so test discovery doesn't trip the
# privilege checks.

import importlib
import pytest
import sys
import types
from pathlib import Path

try:
    importlib.import_module('yaml')
except Exception as exc:
    raise RuntimeError('PyYAML required for tests') from exc

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from privilege_lint._env import HAS_NODE, HAS_GO, HAS_DMYPY, NODE, GO, DMYPY


sys.modules['requests'] = types.ModuleType('requests')
sys.modules['requests'].get = lambda *a, **k: None
sys.modules['requests'].post = lambda *a, **k: None
sys.modules['requests'].request = lambda *a, **k: None

for name in ['pyesprima', 'sarif_om']:
    try:
        importlib.import_module(name)
    except Exception:
        sys.modules[name] = types.ModuleType(name)


def pytest_configure(config):
    config.addinivalue_line('markers', 'requires_node: skip if node missing')
    config.addinivalue_line('markers', 'requires_go: skip if go missing')
    config.addinivalue_line('markers', 'requires_dmypy: skip if dmypy missing')
    config.addinivalue_line('markers', 'network: tests that mock HTTP calls')


def pytest_addoption(parser):
    parser.addoption(
        '--run-network',
        action='store_true',
        default=False,
        help='run tests marked as network'
    )


def pytest_collection_modifyitems(config, items):
    for item in items:
        if 'requires_node' in item.keywords and not HAS_NODE:
            item.add_marker(pytest.mark.skip(reason=f'node missing: {NODE.info}'))
        if 'requires_go' in item.keywords and not HAS_GO:
            item.add_marker(pytest.mark.skip(reason=f'go missing: {GO.info}'))
        if 'requires_dmypy' in item.keywords and not HAS_DMYPY:
            item.add_marker(pytest.mark.skip(reason=f'dmypy missing: {DMYPY.info}'))
        if 'network' in item.keywords and not config.getoption('--run-network'):
            item.add_marker(pytest.mark.skip(reason='network test skipped: add --run-network to run'))
