from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.no_legacy_skip

REPO_ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_CONFTEST = REPO_ROOT / "tests" / "integration" / "conftest.py"


def _load_integration_conftest():
    spec = importlib.util.spec_from_file_location(
        "sentientos_integration_conftest_under_test",
        INTEGRATION_CONFTEST,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_integration_conftest_does_not_mutate_item_keywords_directly() -> None:
    tree = ast.parse(INTEGRATION_CONFTEST.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert not (
                isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "keywords"
                and node.func.attr in {"pop", "popitem", "clear", "update", "setdefault"}
            )
        if isinstance(node, (ast.Delete, ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = []
            if isinstance(node, ast.Delete):
                targets = list(node.targets)
            elif isinstance(node, ast.Assign):
                targets = list(node.targets)
            else:
                targets = [node.target]
            for target in targets:
                assert not (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Attribute)
                    and target.value.attr == "keywords"
                )


def test_integration_skip_override_uses_marker_metadata_without_keywords_access() -> None:
    integration_conftest = _load_integration_conftest()

    class IntegrationItem:
        fspath = Path("tests/integration/test_chat_mistral_runtime.py")
        own_markers = [SimpleNamespace(name="skip"), SimpleNamespace(name="legacy")]

        @property
        def keywords(self):  # pragma: no cover - the assertion is the behavior under test.
            raise AssertionError("integration conftest must not mutate or inspect item.keywords")

    item = IntegrationItem()

    integration_conftest.pytest_collection_modifyitems(SimpleNamespace(), [item])

    assert [marker.name for marker in item.own_markers] == ["legacy"]


def test_integration_skip_override_leaves_non_integration_items_unchanged() -> None:
    integration_conftest = _load_integration_conftest()
    skip_marker = SimpleNamespace(name="skip")
    unit_item = SimpleNamespace(
        fspath=Path("tests/test_chat_service_lazy_loading.py"),
        own_markers=[skip_marker],
    )

    integration_conftest.pytest_collection_modifyitems(SimpleNamespace(), [unit_item])

    assert unit_item.own_markers == [skip_marker]
