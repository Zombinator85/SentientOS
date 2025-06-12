import pytest

@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    for item in items:
        if 'tests/integration' in str(item.fspath):
            # Remove skip markers added by parent conftest
            item.keywords.pop('skip', None)
            item.own_markers = [m for m in item.own_markers if m.name != 'skip']
