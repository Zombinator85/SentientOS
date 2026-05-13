import pytest


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    for item in items:
        if 'tests/integration' in str(item.fspath):
            # Remove skip markers added by parent conftest without mutating
            # pytest's keywords mapping, which is intentionally not deletable.
            item.own_markers = [marker for marker in item.own_markers if marker.name != 'skip']
