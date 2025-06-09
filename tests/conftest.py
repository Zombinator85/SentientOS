import pytest
import sys
import types
import shutil


sys.modules['requests'] = types.ModuleType('requests')
sys.modules['requests'].get = lambda *a, **k: None
sys.modules['requests'].post = lambda *a, **k: None
sys.modules['requests'].request = lambda *a, **k: None


def pytest_configure(config):
    config.addinivalue_line('markers', 'requires_node: skip if node missing')
    config.addinivalue_line('markers', 'requires_go: skip if go missing')
    config.addinivalue_line('markers', 'requires_dmypy: skip if dmypy missing')


def pytest_runtest_setup(item):
    if 'requires_node' in item.keywords and shutil.which('node') is None:
        pytest.skip('node not installed')
    if 'requires_go' in item.keywords and shutil.which('go') is None:
        pytest.skip('go not installed')
    if 'requires_dmypy' in item.keywords and shutil.which('dmypy') is None:
        pytest.skip('dmypy not installed')
