import pytest

from tests.legacy_policy import LEGACY_SKIP_REASON, is_legacy_candidate, legacy_marker_enabled

pytestmark = pytest.mark.no_legacy_skip


def test_legacy_marker_enabled() -> None:
    assert legacy_marker_enabled(None) is False
    assert legacy_marker_enabled("") is False
    assert legacy_marker_enabled("legacy") is True
    assert legacy_marker_enabled("legacy and not slow") is True


def test_legacy_candidate_detection() -> None:
    allowed = {"tests.allowed_module"}
    assert (
        is_legacy_candidate(
            module_name="tests.other_module",
            path_str="tests/test_other_module.py",
            test_name="test_feature",
            keywords={},
            allowed_modules=allowed,
        )
        is True
    )
    assert (
        is_legacy_candidate(
            module_name="tests.allowed_module",
            path_str="tests/test_allowed_module.py",
            test_name="test_feature",
            keywords={},
            allowed_modules=allowed,
        )
        is False
    )
    assert LEGACY_SKIP_REASON.startswith("legacy test disabled")
